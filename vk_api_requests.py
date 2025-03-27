
import re
import requests
import asyncio
import urllib
import string
import random
import os

from typing import Final
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from env import CLIENT_SECRET, CLIENT_ID
from database import *
VERSION: Final = '5.199'

scheduler = AsyncIOScheduler()


def get_access_token_with_refresh_token(refresh_token, device_id):
    """
    Получает новый access_token с использованием refresh_token.

    :param client_id: ID вашего приложения VK.
    :param client_secret: Секретный ключ вашего приложения VK.
    :param refresh_token: Refresh token, полученный ранее.
    :return: Новый access_token.
    """
    url = 'https://id.vk.com/oauth2/auth'
    le_state = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    params = {
        'grant_type': 'refresh_token',
        'client_id': CLIENT_ID,
        'device_id': device_id,
        'refresh_token': refresh_token,
        'state': le_state
    }

    response = requests.post(url, data=params)

    if response.status_code == 200:
        data = response.json()
        return data.get('access_token'), data.get('refresh_token')
    else:
        raise Exception(f"Ошибка при получении access_token: {response.status_code} - {response.text}")

def update_access_tokens():
    """
    Обновляет access_token для всех пользователей в базе данных.
    """
    users = get_users()

    for user in users:
        tg_id, refresh_token, device_id = user
        try:
            new_access_token, new_refresh_token = get_access_token_with_refresh_token(refresh_token, device_id)
            if new_access_token != None and new_refresh_token != None:
                update_token(tg_id, new_access_token, new_refresh_token)
                print(f"Обновлен access_token для пользователя с tg_id: {tg_id}")
            else:
                print(f"Ошибка при обновлении токена у пользователяс tg_id: {tg_id}")
        except Exception as e:
            print(f"Ошибка при обновлении access_token для пользователя с tg_id: {tg_id} - {e}")


def get_group_name_and_id(group_link, access_token):
    match = re.search(r'vk\.com/(.+)', group_link)
    
    if match:
        group_name = match.group(1)  
    else:
        print("Некорректная ссылка группы.")
        return None, None

    url = "https://api.vk.com/method/groups.getById"
    params = {
        'group_id': group_name,  
        'access_token': access_token,
        'v': VERSION
    }
    encoded_params = urllib.parse.urlencode(params)
    response = requests.get(url, params=encoded_params)
    result = response.json()
    
    if 'error' in result:
        print(f"Ошибка: {result['error']['error_msg']}")
        return None, None
    
    group_info = result.get('response')
    if group_info:
        return group_name, group_info['groups'][0]['id'] 
    return None, None   

async def upload_and_publish_video(group_id: int, description: str, temp_file_path: str, tg_id: int):
    access_token = get_token_by_tg_id(tg_id)
    params = {
        'title': description,
        'access_token': access_token,
        'group_id': group_id,
        'description': description,
        'v': VERSION
    }
    encoded_params = urllib.parse.urlencode(params)
    access_token = get_token_by_tg_id(tg_id)
    response = requests.post('https://api.vk.com/method/video.save', params=encoded_params)
    raw = response.json()
    
    if 'response' not in raw:
        raise Exception(raw)

    upload_url = raw['response']['upload_url']
    video_id = raw['response']['video_id']

    with open(temp_file_path, 'rb') as video_file:
        video_file_bytes = video_file.read()

    upload_response = requests.post(upload_url, files={'video_file': video_file_bytes})

    if upload_response.status_code != 200:
        print(f"Ошибка при загрузке видео: {upload_response.text}")
        return None

    post_url = 'https://api.vk.com/method/wall.post'
    post_params = {
        'owner_id': -group_id,
        'from_group': 1,
        'attachments': f'video{-group_id}_{video_id}',
        'access_token': access_token,
        'v': VERSION
    }
    encoded_post_params = urllib.parse.urlencode(post_params)
    access_token = get_token_by_tg_id(tg_id)
    post_response = requests.post(post_url, params=encoded_post_params)

    if post_response.status_code != 200:
        print(f"Ошибка при публикации видео: {post_response.text}")
        return None

    try:
        os.remove(temp_file_path)
        print(f"Временный файл {temp_file_path} успешно удален.")
    except Exception as e:
        print(f"Ошибка при удалении временного файла {temp_file_path}: {e}")

    return post_response.json()

async def schedule_video_publish(group_id: int, tg_id: int, publish_time: datetime, description: str, temp_file_path: str):
    scheduler.add_job(lambda: asyncio.run(upload_and_publish_video(group_id, description, temp_file_path, tg_id)), 'date', run_date=publish_time)

def check_vk_token(user_access_token):
    url = "https://api.vk.com/method/secure.checkToken"
    params = {
        'access_token': CLIENT_SECRET,
        'token': user_access_token,
        'v': VERSION
    }

    encoded_params = urllib.parse.urlencode(params)
    response = requests.get(url, params=encoded_params)
    result = response.json()
    
    if 'error' in result:
        return False  

    if 'response' in result and result['response'].get('success') == 1:
        return True  

    return False  
