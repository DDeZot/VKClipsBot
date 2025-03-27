from typing import Final

from dotenv import load_dotenv
import os


dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


BOT_TOKEN: Final = os.environ.get('BOT_TOKEN', 'define me!')
CLIENT_ID: Final =  os.environ.get('CLIENT_ID', 'define me!')
CLIENT_SECRET: Final = os.environ.get('CLIENT_SECRET', 'define me!')