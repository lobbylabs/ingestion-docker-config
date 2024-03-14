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

fastapi_app = FastAPI()


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
    route_prefix="/v1/links",
    ray_actor_options={"num_cpus": .25},
    max_concurrent_queries=20,
    num_replicas=int(os.environ.get("NUM_REPLICAS_LINKS", 10))
    # max_replicas_per_node=100
)
@serve.ingress(fastapi_app)
class LinkFetcherDeployment:
    def __init__(self):
        print("init")

    @fastapi_app.post("/")
    async def root(self, request: WebScrapeModel):
        job = Job(JavaScriptSpider, start_urls=request.urls,
                  depth=request.depth)
        processor = Processor(settings=get_project_settings())
        items = processor.run([job])

        # Format the response
        response = {"data": items}
        return response


app = LinkFetcherDeployment.bind()
