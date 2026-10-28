import asyncio, logging
from .app import App

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

if __name__ == "__main__":
    asyncio.run(App().run())
