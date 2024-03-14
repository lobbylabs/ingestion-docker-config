from ray import serve
from fastapi import FastAPI
import os
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

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

    @fastapi_app.post("/v1/content")
    async def fetcher(self, request: WebContentFetchModel):
        print("URL:", request.url)

        try:
            self.driver.get(request.url)
        except Exception as e:
            return {"url": request.url, "status": 402, "message": e}

        visible_texts = []

        elements = self.driver.find_elements(By.XPATH, "//*")

        # Iterate through the elements
        for element in elements:
            try:
                if element.is_displayed():
                    text = element.text.strip()
                    if text:  # Ensure text is not empty
                        visible_texts.append(text)
            except Exception as e:
                pass

        visible_text = ' '.join(visible_texts)
        return {"url": request.url, "content": visible_text}


app = ContentFetcher.bind()
