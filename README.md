pip install -r requirements.txt

serve run scraper_app:web_scraper_app --host 0.0.0.0 --port 8100
serve build scraper_app:web_scraper_app -o ./web-scraper.yaml

docker compose up -d --build
docker compose logs -f