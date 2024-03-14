pip install -r requirements.txt

serve run app:web_scraper_app content_app:app --host 0.0.0.0 --port 8100
serve build links_app:app content_app:app -o ./web-scraper.yaml

serve build scraper_app:web_scraper_app scraper_app:content_fetcher_app scraper_app:link_fetcher_app -o web-scraper-app.yaml

docker compose up -d --build
docker compose logs -f