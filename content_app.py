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
fastapi_app = FastAPI()


class WebContentFetchModel(BaseModel):
    url: str

@serve.deployment(
    route_prefix="/v1/content",
    ray_actor_options={"num_cpus": .25},
    max_concurrent_queries=50,
    num_replicas=int(os.environ.get("NUM_REPLICAS_CONTENT", 30))
)
@serve.ingress(fastapi_app)
class ContentFetcher:
    def __init__(self):
        chrome_options = Options()
        # Runs Chrome in headless mode.
        chrome_options.add_argument("--headless")
        self.driver = webdriver.Chrome(options=chrome_options)
        print("init")

    @fastapi_app.post("/")
    async def fetcher(self, request: WebContentFetchModel):
        print("URL:", request.url)

        try:
            self.driver.get(request.url)
        except Exception as e:
            return {"url": request.url, "status": 402, "message": e}

        root_element = self.driver.find_element(By.XPATH, '//html')

        return {"url": request.url, "content": str(root_element.text)}

        


app = ContentFetcher.bind()
