import logging
import sqlite3
import asyncio
import pytz
import aiohttp
import string
import base64
import random
import hashlib
import moviepy as mp

from typing import Final
from urllib.parse import urlparse, parse_qs
from aiogram.enums.parse_mode import ParseMode
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, BaseFilter
from aiogram.types.inline_keyboard_button import InlineKeyboardButton
from aiogram.types.inline_keyboard_markup import InlineKeyboardMarkup
from aiogram.types.bot_command import BotCommand
from aiohttp import ClientSession
from datetime import datetime, timedelta

from env import BOT_TOKEN, CLIENT_ID, CLIENT_SECRET
from database import *
from vk_api_requests import *

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

REDIRECT_URL: Final = 'https://oauth.vk.com/blank.html'
SCOPE: Final = 'wall,video,offline'  

class FormStates(StatesGroup):
    waiting_for_redirect = State()
    waiting_username_to_add = State()
    waiting_username_to_remove = State()
    add_group_link = State()
    add_group_description = State()
    waiting_group_description = State()


class UploadStates(StatesGroup):
    choosing_channel = State()
    specifying_video_count = State()
    specifying_publish_time = State()
    waiting_for_videos = State()
    all_upload = State()

class IsAdmin(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM tg_users WHERE tg_id=?", (message.from_user.id,))
        result = cursor.fetchone()
        conn.close()
        return (result and result[0] == True)

async def cmd_start(message: types.Message) -> None:
    add_user_if_not_exists(message.from_user.id, message.from_user.username)
    if await IsAdmin()(message):
        await message.answer("Добро пожаловать! Используйте команды, предложенные в меню.")
        return
    else: 
        await message.answer("Добро пожаловать! К сожалению, у Вас нет доступа к использованию бота.")
        return

async def cmd_add_admin(message: types.Message, state: FSMContext) -> None:
    await message.answer('Чтобы выдать права администратора пользователю, введите его никнейм без @:')
    await state.set_state(FormStates.waiting_username_to_add)

async def cmd_remove_admin(message: types.Message, state: FSMContext) -> None:
    await message.answer('Чтобы отобрать права администратора у пользователя, введите его никнейм без @:')
    await state.set_state(FormStates.waiting_username_to_remove)

def generate_code_verifier(length=128):
    """Генерация случайной строки для code_verifier."""
    characters = string.ascii_letters + string.digits + '-._~'
    return ''.join(random.choice(characters) for _ in range(length))

def generate_code_challenge(code_verifier):
    """Генерация code_challenge из code_verifier."""
    code_verifier_bytes = code_verifier.encode('utf-8')
    hashed = hashlib.sha256(code_verifier_bytes).digest()
    return base64.urlsafe_b64encode(hashed).decode('utf-8').rstrip('=')

def generate_auth_url(client_id, redirect_uri, state, code_challenge):
    return (
        f'https://id.vk.com/authorize?'
        f'response_type=code&'
        f'client_id={client_id}&'
        f'redirect_uri={redirect_uri}&'
        f'state={state}&'
        f'code_challenge={code_challenge}&'
        f'code_challenge_method=S256&'
        f'scope={SCOPE}'
    )
    
async def exchange_code_for_token(code, device_id, client_id, redirect_uri, code_verifier):
    token_url = 'https://id.vk.com/oauth2/auth'
    params = {
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'device_id': device_id,
        'code_verifier': code_verifier
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                error_response = await response.json()
                print(f"Ошибка: {error_response}")
                return None

async def cmd_start_auth(message: types.Message, state: FSMContext):
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    le_state = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

    auth_url = generate_auth_url(CLIENT_ID, REDIRECT_URL, le_state, code_challenge)

    await message.answer(
        "Нажмите на кнопку ниже для авторизации через VK ID. Далее напишите сюда адрес страницы куда вас перенаправили.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
            types.InlineKeyboardButton(text="Авторизоваться", url=auth_url)]]
        )
    )
    
    await state.update_data(code_verifier=code_verifier)
    await state.set_state(FormStates.waiting_for_redirect)      
    
async def process_redirect(message: types.Message, state: FSMContext):
    parsed_url = urlparse(message.text.strip())
    query_params = parse_qs(parsed_url.query)

    code = query_params.get('code', [None])[0]
    device_id = query_params.get('device_id', [None])[0]
    data = await state.get_data()
    code_verifier = data.get('code_verifier')
    if not code:
        await message.answer("Код авторизации не получен. Пожалуйста, проверьте URL.")
        return

    tokens = await exchange_code_for_token(code, device_id, CLIENT_ID, REDIRECT_URL, code_verifier)
    
    if tokens:
        access_token = tokens.get('access_token')
        refresh_token = tokens.get('refresh_token')
        id_token = tokens.get('id_token')
        
        await message.answer(f"Токен успешно сохранен!")
        update_token_info(message.from_user.id, access_token, refresh_token, id_token, device_id)
    else:
        await message.answer(f"ошибка при получении токена")


async def cmd_delete_group(message: types.Message):
    groups = get_vk_groups()
    
    if not groups:
        await message.answer("Нет доступных групп для удаления.")
        return
    
    keyboard = []
    for group_id, group_name in groups:
        keyboard.append([InlineKeyboardButton(text=group_name, callback_data=f'delete_{group_id}')])
    await message.answer("Выберите группу для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

async def cmd_edit_group_description(message: types.Message):
    groups = get_vk_groups()  
    
    if not groups:
        await message.answer("Нет доступных групп для редактирования.")
        return
    
    keyboard = []
    for group_id, group_name in groups:
        keyboard.append([InlineKeyboardButton(text=group_name, callback_data=f'edit_{group_id}')])

    await message.answer("Выберите группу для редактирования:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

async def cmd_add_group(message: types.Message, state: FSMContext):
    await state.set_state(FormStates.add_group_link)
    await message.answer("Пожалуйста, введите ссылку на группу ВК:")
    return

async def cmd_upload(message: types.Message, state: FSMContext):
    groups = get_vk_groups() 
    
    if not groups:
        await message.answer("Нет доступных групп для загрузки видео.")
        return
    
    keyboard = []
    for group_id, group_name in groups:
        keyboard.append([InlineKeyboardButton(text=group_name, callback_data=f'channel_{group_id}')])
    
    await message.answer("Выберите канал:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await state.set_state(UploadStates.choosing_channel)
    return

async def process_add_admin(message: types.Message, state: FSMContext) -> None:
    try:    
        set_user_admin(message.text)
        message.answer('Пользователь успешно добавлен в администраторы!')
        await state.clear()
    except Exception as e:  
        await message.answer('Пользователь с таким ником не найден')

async def process_remove_admin(message: types.Message, state: FSMContext) -> None:
    try:    
        revoke_admin_rights(message.text)
        await message.answer('Пользователь успешно удален из администраторов!')
        await state.clear()
    except Exception as e:  
        await message.answer('Пользователь с таким ником не найден')

async def process_group_link(message: types.Message, state: FSMContext):
    link = message.text
    group_name, group_id = get_group_name_and_id(group_link=link, access_token=get_token_by_tg_id(message.from_user.id))
    
    if group_id is None:
        await message.answer("Не удалось получить ID группы. Убедитесь, что ссылка правильная.")
        return

    await state.update_data(group_link=link, group_name=group_name, group_id=group_id)
    await state.set_state(FormStates.add_group_description)
    await message.answer("Введите описание, которым надо будет дополнять видео, публикуемые в этой группе:")

    await state.update_data(group_link=link, group_name=group_name, group_id=group_id)
    await state.set_state(FormStates.add_group_description)
    await message.answer("Введите описание, которым надо будет дополнять видео, публикуемые в этой группе:")

async def process_group_description(message: types.Message, state: FSMContext):
    description = message.text.strip()
    user_data = await state.get_data()
    save_vk_group(group_name=user_data['group_name'], group_link=user_data['group_link'], description=description, group_id=user_data['group_id'])
    await message.answer(f"Группа успешно добавлена:\nСсылка: {user_data['group_link']}\nОписание: {description}")
    await state.clear()

async def process_delete_group(callback_query: types.CallbackQuery):
    group_id = int(callback_query.data.split('_')[1])
    group_name = get_vk_group_id_by_name(group_id)
    
    if delete_vk_group(group_id):
        await bot.answer_callback_query(callback_query.id) 
        await bot.send_message(callback_query.from_user.id, f"Группа {group_name} успешно удалена.")
    else:
        await bot.send_message(callback_query.from_user.id, "Произошла ошибка при удалении группы.")

async def process_edit_group_description(callback_query: types.CallbackQuery,state: FSMContext):
    group_id = int(callback_query.data.split('_')[1])  
    group_name = get_vk_group_id_by_name(group_id)

    await bot.answer_callback_query(callback_query.id)  
    await bot.send_message(callback_query.from_user.id, f"Введите новое описание для группы {group_name}:")
    await state.update_data(group_id=group_id)
    await state.set_state(FormStates.waiting_group_description)

async def handle_new_description(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    
    if 'group_id' in user_data:
        group_id = user_data['group_id']
        new_description = message.text
        
        if update_group_description(group_id, new_description):
            await message.answer(f"Описание группы с ID {group_id} успешно обновлено.")
            await state.clear()
        else:
            await message.answer("Произошла ошибка при обновлении описания группы.")

async def process_channel_selection(callback_query: types.CallbackQuery, state: FSMContext):
    group_id = int(callback_query.data.split('_')[1])  
    group_name = get_vk_group_id_by_name(group_id)
    group_link = get_group_link(group_id)
    await state.update_data(group_id=group_id, group_name=group_name, group_link=group_link)  
    
    await bot.answer_callback_query(callback_query.id) 
    await bot.send_message(callback_query.from_user.id, "Сколько видео хотите опубликовать?")
    
    await state.set_state(UploadStates.specifying_video_count)

async def process_video_count(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("Пожалуйста, введите корректное количество видео.")
        return
    
    video_count = int(message.text)
    
    await state.update_data(video_count=video_count)  
    await message.answer("В какое время их выложить? \n\n(Формат: 'ДД ЧЧ:ММ' или 'ЧЧ:ММ')\n\nЧасовой пояс: Екатеринбург(МСК+2, GMT+5))")
    
    await state.set_state(UploadStates.specifying_publish_time)
    
async def process_publish_time(message: types.Message, state: FSMContext):
    now = datetime.now(tz=pytz.timezone('Asia/Yekaterinburg'))
    parts = message.text.split()
    
    if len(parts) == 1:

        time_string = parts[0]
        day = now.day 
    elif len(parts) == 2:
        day, time_string = parts
        day = int(day)  
    else:
        await message.answer("Пожалуйста, введите корректное время в формате 'ДД ЧЧ:ММ' или 'ЧЧ:ММ'.")
        return

    date_string = f"{now.year}-{now.month:02d}-{day:02d} {time_string}"

    try:
        publish_time = datetime.strptime(date_string, "%Y-%m-%d %H:%M")
        
        if publish_time.day < now.day or publish_time.time() < now.time():
            await message.answer("Пожалуйста, выберите время в будущем.")
            return
        
        await state.update_data(publish_time=publish_time)

        data = await state.get_data()
        video_count = data.get('video_count')

        await message.answer(f"Пожалуйста, отправьте {video_count} видео.")
        
        await state.update_data(videos=[])
        await state.set_state(UploadStates.waiting_for_videos)

    except ValueError:
        await message.answer("Некорректный формат времени. Пожалуйста, используйте формат 'ДД ЧЧ:ММ' или 'ЧЧ:ММ'.")

async def download_video_with_timeout(video_id, timeout=60):
    """
    Функция для скачивания видео с таймаутом.
    """
    return await asyncio.wait_for(bot.download(video_id), timeout)

async def process_video(message: types.Message, state: FSMContext):
    try:
        video = message.video
        temp_file_path = f"temp/{video.file_id}.mp4"
        data = await state.get_data()
        videos = data.get('videos', [])
        messages = data.get('messages', [])
        if os.path.exists(temp_file_path):
            videos.append(temp_file_path)
            await state.update_data(videos=videos)
            return

        attempt = 0
        while attempt < 3:
            try:
                downloaded = await download_video_with_timeout(video.file_id, timeout=60)
                break
            except asyncio.TimeoutError:
                attempt += 1
                print(f"Попытка {attempt}: Ошибка таймаута при скачивании видео. Повторная попытка через 5 секунд...")
                await asyncio.sleep(5)
        else:
            await message.reply('Не удалось скачать видео после нескольких попыток.')
            return

        with open(temp_file_path, 'wb') as temp_file:
            temp_file.write(downloaded.read())

        if video.duration >= 60:
            video_clip = mp.VideoFileClip(temp_file_path)
            trimmed_clip: mp.VideoFileClip = video_clip.subclipped(0, 59)

            trimmed_clip.write_videofile(
                temp_file_path,
                codec="libx264",
                audio_codec="aac",
                fps=video_clip.fps,
                bitrate="3000k", 
                ffmpeg_params=["-preset", "ultrafast"]  
            )
            trimmed_clip.close()
            video_clip.close()

        videos.append(temp_file_path)

        if len(videos) != 0:
            await state.update_data(videos=videos)

    except TypeError as e:
        print(e)
        await message.reply('Неправильный формат видеофайла')
    except Exception as e:
        print(e)
        await message.reply('Произошла ошибка при загрузке, можете попробовать загрузить файл еще раз')

    video_count = data.get('video_count')
        
    if messages:
        for msg_id in messages:
            await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
            messages.remove(msg_id)

    if len(videos) < video_count:
        remaining_videos = video_count - len(videos)

        if remaining_videos > 0 and not messages:
            msg = await message.answer(f"Осталось загрузить {remaining_videos} видео.")
            messages.append(msg.message_id)

        await state.update_data(messages=messages)
        return
    
    if len(videos) == video_count:
        msg = await message.answer("Все видео загружены!")
        await state.set_state(UploadStates.all_upload)
        await state.update_data(videos=videos)  
        await upload_all_videos(message, state)

async def upload_all_videos(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    videos = data.get('videos', [])
    group_id = data.get('group_id')
    group_name = data.get('group_name')
    group_link = data.get('group_link')
    publish_time = data.get('publish_time')

    if publish_time is None:
        await message.answer("Не указано время публикации.")
        return

    publish_time_str = f"{publish_time.day}.{publish_time.month} в {publish_time.hour}:{publish_time.minute}"
    
    description = get_group_description(group_id)
    user_tg_id = message.from_user.id

    for i, video_path in enumerate(videos):
        if i > 0 and i % 3 == 0:
            publish_time += timedelta(seconds=20)

        await schedule_video_publish(
            group_id=group_id,
            tg_id=user_tg_id,
            publish_time=publish_time,
            description=description,
            temp_file_path=video_path
        )

    await state.clear()
    await message.answer(
        f"{len(videos)} видео будет выложено начиная с {publish_time_str} в группе <a href='{group_link}'>{group_name}</a>.",
        parse_mode=ParseMode.HTML
    )

    yekaterinburg_tz = pytz.timezone('Asia/Yekaterinburg')
    publish_time_aware = publish_time.replace(tzinfo=yekaterinburg_tz)

    wait_time = (publish_time_aware - datetime.now(yekaterinburg_tz)).total_seconds() - 1800    
    await asyncio.sleep(wait_time)
    await message.answer(f"{len(videos)} видео выложено в группе <a href='{group_link}'>{group_name}</a>.", parse_mode=ParseMode.HTML)

def register_handlers() -> None:
    dp.message.register(cmd_start, Command('start'))
    dp.message.register(cmd_start_auth, Command('get_access_token'), IsAdmin())
    dp.message.register(cmd_add_group, Command('add_group'), IsAdmin())
    dp.message.register(cmd_delete_group, Command('delete_group'), IsAdmin())
    dp.message.register(cmd_edit_group_description, Command('edit_group_description'), IsAdmin())
    dp.message.register(cmd_upload, Command('upload'), IsAdmin())
    dp.message.register(cmd_add_admin, Command('add_admin'), IsAdmin())
    dp.message.register(cmd_remove_admin, Command('remove_admin'), IsAdmin())

    dp.message.register(process_redirect, FormStates.waiting_for_redirect, IsAdmin())
    dp.message.register(process_group_link, FormStates.add_group_link, IsAdmin())
    dp.message.register(process_group_description, FormStates.add_group_description, IsAdmin())
    dp.message.register(handle_new_description, FormStates.waiting_group_description, IsAdmin())
    dp.message.register(process_add_admin, FormStates.waiting_username_to_add, IsAdmin())
    dp.message.register(process_remove_admin, FormStates.waiting_username_to_remove, IsAdmin())

    dp.message.register(process_video_count, UploadStates.specifying_video_count, IsAdmin())
    dp.message.register(process_publish_time, UploadStates.specifying_publish_time, IsAdmin())
    dp.message.register(process_video, UploadStates.waiting_for_videos, IsAdmin())
    dp.message.register(upload_all_videos, UploadStates.all_upload, IsAdmin())

    dp.callback_query.register(process_delete_group, lambda c: c.data.startswith('delete_'), IsAdmin())
    dp.callback_query.register(process_edit_group_description, lambda c: c.data.startswith('edit_'), IsAdmin())
    dp.callback_query.register(process_channel_selection, UploadStates.choosing_channel, lambda c: c.data.startswith('channel_'), IsAdmin())

async def main():
    scheduler.timezone = pytz.timezone('Asia/Yekaterinburg')
    scheduler.add_job(update_access_tokens, 'cron', minute='*')    
    scheduler.start()
    register_handlers()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())