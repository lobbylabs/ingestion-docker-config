import os
from ray import serve
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import logging
from scrapy.spiders import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor
from scrapy.utils.project import get_project_settings

from scrapyscript import Job, Processor
from ray import serve
from fastapi import FastAPI
import os
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
from ray.serve.handle import DeploymentHandle, DeploymentResponse

class WebScrapeModel(BaseModel):
    depth: int
    urls: List[str]


class JavaScriptSpider(CrawlSpider):
    name = 'javascript_spider'

    rules = (
        Rule(LinkExtractor(deny_domains=['localhost']),
             callback='parse_item', follow=True),
    )

    def __init__(self, *args, **kwargs):
        logger = logging.getLogger("scrapy.spidermiddlewares.depth")
        logger.setLevel(logging.ERROR)
        logger2 = logging.getLogger("scrapy.core.scraper")
        logger2.setLevel(logging.ERROR)
        logger3 = logging.getLogger("scrapy.core.engine")
        logger3.setLevel(logging.ERROR)
        logger4 = logging.getLogger("scrapy.downloadermiddlewares.redirect")
        logger4.setLevel(logging.ERROR)
        super().__init__(*args, **kwargs)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        if "depth" in kwargs:
            spider.settings.set(
                "DEPTH_LIMIT", kwargs["depth"], priority="spider"
            )
        # spider.settings.set("TWISTED_REACTOR", "twisted.internet.asyncioreactor.AsyncioSelectorReactor", priority="spider")
        # spider.settings.set(
        #     "DEPTH_PRIORITY", 1, priority="spider"
        # )
        # spider.settings.set(
        #     "SCHEDULER_DISK_QUEUE", "scrapy.squeues.PickleFifoDiskQueue", priority="spider"
        # )
        # spider.settings.set(
        #     "SCHEDULER_MEMORY_QUEUE", "scrapy.squeues.FifoMemoryQueue", priority="spider"
        # )
        return spider

    async def parse_item(self, response):
        item = {
            'url': response.url,
            'meta': response.meta
        }
        yield item


@serve.deployment(
    ray_actor_options={"num_cpus": .25},
    max_concurrent_queries=20,
    num_replicas=int(os.environ.get("NUM_REPLICAS_LINKS", 10))
    # max_replicas_per_node=100
)
class LinkFetcher:
    def __init__(self):
        print("init")

    async def __call__(self, request: WebScrapeModel):
        job = Job(JavaScriptSpider, start_urls=request.urls,
                  depth=request.depth)
        processor = Processor(settings=get_project_settings())
        items = processor.run([job])

        # Format the response
        response = {"data": items}
        return response



class WebContentFetchModel(BaseModel):
    url: str

@serve.deployment(
    ray_actor_options={"num_cpus": .25},
    max_concurrent_queries=50,
    num_replicas=int(os.environ.get("NUM_REPLICAS_CONTENT", 30))
)
class ContentFetcher:
    def __init__(self):
        chrome_options = Options()
        # Runs Chrome in headless mode.
        chrome_options.add_argument("--headless")
        self.driver = webdriver.Chrome(options=chrome_options)
        print("init")

    async def __call__(self, request: WebContentFetchModel):
        print("URL:", request.url)

        try:
            self.driver.get(request.url)
        except Exception as e:
            return {"url": request.url, "status": 402, "message": e}

        root_element = self.driver.find_element(By.XPATH, '//html')

        return {"url": request.url, "content": str(root_element.text)}















class WebScrapeRequestModel(BaseModel):
    depth: int
    urls: List[str]


fastapi_app = FastAPI()

@serve.deployment(
    route_prefix="/v1/web_scraper",
    ray_actor_options={"num_cpus": .25},
    max_concurrent_queries=20,
    num_replicas=1
    # max_replicas_per_node=100
)
@serve.ingress(fastapi_app)
class WebScraperDeployment:
    def __init__(self, link_fetcher_handle: DeploymentHandle, content_fetcher_handle: DeploymentHandle):
        self._downstream_link_fetcher_handle = link_fetcher_handle
        self._downstream_content_fetcher_handle = content_fetcher_handle

    @fastapi_app.post("/")
    async def root(self, request: WebScrapeRequestModel):
        
        scraped_links = await self._downstream_link_fetcher_handle.remote(WebScrapeModel(depth=request.depth, urls = request.urls))





        
        return {"data": scraped_links}


web_scraper_app = WebScraperDeployment.bind(LinkFetcher.bind(), ContentFetcher.bind())