import os
from ray import serve
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import logging
from scrapy.spiders import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor
from scrapy.utils.project import get_project_settings
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
import uuid
import ray
import time
from scrapy import signals
from scrapy.crawler import CrawlerProcess, CrawlerRunner
from twisted.internet import reactor
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import ray
import json
import asyncio
from scrapy import signals
from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings
from scrapy.spiders import Spider
from pydantic import BaseModel, HttpUrl
from typing import List, Optional
from urllib.parse import urlparse, urljoin
from typing import Set, List
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from fastapi import BackgroundTasks, FastAPI
import requests

class ScrapeTask(BaseModel):
    start_url: str
    depth: Optional[int] = 1
    same_route: Optional[bool] = False
    same_domain: Optional[bool] = False
    max_links_page: Optional[int] = 20
    max_links_total: Optional[int] = 200
    task_id: Optional[str] = str(uuid4())

class FindLinksTask(ScrapeTask):
    fltph_: Optional[str] = None

class FindLinksTaskResultFragment(BaseModel):
    url: str
    depth: int

class FindLinksTaskResult(FindLinksTask):
    links: List[FindLinksTaskResultFragment]

class ContentFetchTask(FindLinksTaskResult):
    cftph_: Optional[str] = None

class ContentFetchInput(BaseModel):
    url: str

class ContentFetchOutput(ContentFetchInput):
    content: Optional[str] = None
    error: Optional[str] = None

class ContentFetchTaskResult(ContentFetchTask):
    num_results: int
    content_fetch_results: List[ContentFetchOutput]
    



@ray.remote
class ContentFetcher:
    def __init__(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        self.driver = webdriver.Chrome(options=chrome_options)

    async def fetch_content(self, input: ContentFetchInput) -> ContentFetchOutput:
        append = {}
        try:
            self.driver.get(input.url)
            root_element = self.driver.find_element(By.XPATH, '//html')
            append = {"content": str(root_element.text)}
        except Exception as e:
            append = {"error": str(e)}
        finally:
            return ContentFetchOutput.model_validate({**input.dict(), **append})


def get_base_url_with_path(url):
    """
    Extracts the base URL along with the path up to a point where it's not a file.

    Parameters:
    - url (str): The full URL from which to extract the base URL and path.

    Returns:
    - str: The base URL including the path up to a non-file component.
    """
    # Parse the URL to extract its components.
    parsed_url = urlparse(url)
    path = parsed_url.path
    # Check if the path looks like it ends with a file (contains a dot in the last segment)
    if '.' in path.split('/')[-1]:
        # Remove the last segment which is considered a file
        path = '/'.join(path.split('/')[:-1])
    
    # Ensure the path ends with a '/' to denote it's a directory, unless the path is empty
    if path and not path.endswith('/'):
        path += '/'
    
    # Construct the URL including the path up to the last directory
    base_url_with_path = parsed_url.scheme +parsed_url.netloc + path
    return base_url_with_path

def normalize_url(url, base_url):
    """
    Normalizes a single URL based on a base URL.

    Parameters:
    - url (str): The URL to normalize. Can be an absolute URL, a relative URL, or a URL fragment.
    - base_url (str): The base URL to use for normalization of relative URLs and fragments.

    Returns:
    - str: The normalized URL.
    """
    parsed_url = urlparse(url)
    
    # Check if the URL is absolute. If it has a scheme (e.g., 'http', 'https'), it's absolute.
    if parsed_url.scheme:
        return url
    else:
        # For relative URLs and fragments, join them with the base URL.
        return urljoin(base_url, url)




def extract_links(url, max_links_page, same_route, same_domain):
    links = []
    page = requests.get(url)
    soup = BeautifulSoup(page.content, "html.parser")
    elements = soup.find_all("a", href=True)
    # refine how links are retrieved (filter by type?)
    for element in elements:
        new_url = element["href"]
        new_url = normalize_url(new_url, url)
        parsed_url = urlparse(url)
        parsed_new_url = urlparse(new_url)
        if same_route & (get_base_url_with_path(new_url) != get_base_url_with_path(url)):
            continue
        if same_domain & (parsed_new_url.netloc != parsed_url.netloc):
            continue
        # if (get_base_url_with_path(new_url) == get_base_url_with_path(url)) & urlparse(new_url).fragment == '':
        #     continue
        if parsed_new_url.fragment != '':
            continue
        # print(get_base_url_with_path(new_url))
        links.append(new_url)
    # TODO: refine how max links is determined (filter by quality)
    return set(links[:max_links_page])

def find_all_links(start_url, max_depth, current_depth, max_links_page, same_route, same_domain) -> List[FindLinksTaskResultFragment]:
    print(start_url, max_depth, current_depth, max_links_page, same_route, same_domain)
    
    if current_depth > max_depth:
        return []

    links = set(extract_links(start_url, max_links_page, same_route, same_domain))
    fragments = [FindLinksTaskResultFragment.model_validate({"depth": current_depth, "url": link}) for link in links]

    for url in links:
        new_links = find_all_links(url, max_depth, current_depth+1, max_links_page, same_route, same_domain)
        new_fragments = [FindLinksTaskResultFragment.model_validate({"depth": current_depth, "url": link}) for link in new_links]
        fragments.update(new_fragments)

    return fragments


@ray.remote
def execute_find_links_task(task: FindLinksTask) -> FindLinksTaskResult:
    return FindLinksTaskResult.model_validate({**task.dict(), "links": find_all_links(task.start_url, task.depth, 0, task.max_links_page, task.same_route, task.same_domain)})


@ray.remote
def execute_fetch_content_task(task: ContentFetchTask) -> ContentFetchTaskResult:
    content_fetcher_handle = ContentFetcher.remote()
    start_url_input = ContentFetchInput.model_validate({"url": task.start_url})
    inputs = [ContentFetchInput.model_validate({"url": link["url"]}) for link in task.links]
    inputs.append(start_url_input)
    content_fetch_output_objs = [content_fetcher_handle.fetch_content.remote(input) for input in inputs]
    content_fetch_outputs: List[ContentFetchTaskResult] = ray.get(content_fetch_output_objs)
    return ContentFetchTaskResult.model_validate({**task.dict(), "num_results": len(content_fetch_outputs), "content_fetch_results": content_fetch_outputs})





fastapi_app = FastAPI()


class WebScrapeRequestModel(BaseModel):
    background: Optional[bool] = False
    result_url: Optional[str]
    scrape_tasks: List[ScrapeTask]
    job_id: Optional[str] = str(uuid4())

@serve.deployment(
    route_prefix="/v1/web_scraper",
    ray_actor_options={"num_cpus": .25},
    max_concurrent_queries=20,
    num_replicas=1
    # max_replicas_per_node=100
)
@serve.ingress(fastapi_app)
class WebScraperDeployment:
    def scrape(self, scrape_request: WebScrapeRequestModel):
        try:
            find_link_task_objs = [execute_find_links_task.remote(FindLinksTask.model_validate({**scrape_task.dict()})) for scrape_task in scrape_request.scrape_tasks]
            find_link_tasks_completed: List[FindLinksTaskResult] = ray.get(find_link_task_objs)
            # fetch_content_task_objs = [execute_fetch_content_task.remote(ContentFetchTask.model_validate({**link_task.dict()})) for link_task in find_link_tasks_completed]
            # fetch_content_tasks_completed: List[ContentFetchTaskResult] = ray.get(fetch_content_task_objs)
        except Exception as e:
            if scrape_request.background:
                url = scrape_request.result_url
                requests.post(url, json={"ERROR": str(e)})
                pass
            else: 
                return {"ERROR": str(e)}
        finally:
            if scrape_request.background:
                url = scrape_request.result_url
                requests.post(url, json=[task.dict() for task in find_link_tasks_completed])
                # requests.post(url, json=[task.dict() for task in fetch_content_tasks_completed])
                pass
            else: 
                return find_link_tasks_completed
                # return fetch_content_tasks_completed


    @fastapi_app.post("/")
    async def root(self, scrape_request: WebScrapeRequestModel, background_tasks: BackgroundTasks):

        if scrape_request.background:
            background_tasks.add_task(self.scrape, scrape_request)
            return {"message": "scraping started!", "job_id": scrape_request.job_id}
        else:
            return self.scrape( scrape_request)
        
web_scraper_app = WebScraperDeployment.bind()