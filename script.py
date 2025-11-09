import asyncio
import datetime
import logging
# ---- Import Telethon -----
from telethon import TelegramClient, events, functions
from telethon.errors import FloodWaitError, RPCError
from enum import Enum, auto
from telethon.tl.types import DocumentAttributeSticker
#---------------------------

#------ Types Message ------
class MessageType(Enum):
    TEXT = auto()
    GIF = auto()
    VOICE = auto()
    PHOTO = auto()
    VIDEO = auto()
    STICKER = auto()
    ANIM_STICKER = auto()
    VIDEO_STICKER = auto()

def get_message_types(msg):
    if msg.text:
        return MessageType.TEXT
    if msg.gif:
        return MessageType.GIF
    if msg.voice or msg.audio:
        return MessageType.VOICE
    if msg.photo:
        return MessageType.PHOTO
    if msg.video:
        if msg.document:
            for attr in msg.document.attributes:
                if isinstance(attr, DocumentAttributeSticker):
                    if msg.document.mime_type == "video/webm":
                        return MessageType.VIDEO_STICKER
        return MessageType.VIDEO            
    if msg.sticker:
        mime = getattr(msg.sticker, "mime_type", "")
        if mime == "application/x-tgsticker":
            return MessageType.ANIM_STICKER
        return MessageType.STICKER
    return MessageType.TEXT
#------------------------------------

#--------- Excluded System ----------
_RAW_EXCLUDED_USERNAMES = [
    #Annoying perons username
]
EXCLUDED_USERNAME = {name.lower() for name in _RAW_EXCLUDED_USERNAMES} 
EXCLUDED_CHATID = {1332686440}#<- This is annoying persons chatId from @userinfobot

async def should_exclude(event) -> bool:
    try:
        chat = await event.get_chat()
        sender = await event.get_sender()
    
        uname_sender = sender.username.lower() if sender and sender.username else None
        uname_chat = chat.username.lower() if hasattr(chat, 'username') and chat.username else None
        
        if uname_sender in EXCLUDED_USERNAME or uname_chat in EXCLUDED_USERNAME:
            logger.info(f"Исключено по username: sender=@{uname_sender}")
            return True
        if event.chat_id in EXCLUDED_CHATID:
            logger.info(f"Исключено по chat_id: {event.chat_id} user")
            return True
        return False
    except Exception as e:
        logger.warning(f"Ошибка в should_exclude: {e}")
        return False
#------------------------------------

# ------- Logging -------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("telegram_bot.log")]
)
logger = logging.getLogger(__name__)

logging.getLogger("telethon").setLevel(logging.ERROR)
#------------------------------------

#-------- Constants -----------------
API_ID = 20276453
API_HASH = 'eff651a7a703fab7d6b1aa1c95d48fb0'
SESSION_NAME = 'session_autoread'
KEEPONLINE_INTERVAL = 45
DAY_START = 8
DAY_END = 23

stop_request = False
#------------------------------------

#---------- Day Settings ------------
def is_day() -> bool:
    hour = datetime.datetime.now().hour
    return DAY_START <= hour < DAY_END
#------------------------------------

async def keep_online_task(client: TelegramClient):
    global stop_request
    while not stop_request:
        try:
            if not client.is_connected():
                logger.warning("Клиент не подключен, попытка переподключения...")
                await client.connect()
            offline = not is_day()
            await client(functions.account.UpdateStatusRequest(offline=offline))
            logger.debug(f"Статус обновлен: {'offline' if offline else 'online'}")
        except FloodWaitError as e:
            logger.warning(f"FloodWait: ожидание {e.seconds} секунд")
            await asyncio.sleep(e.seconds + 1)
        except RPCError as e:
            logger.error(f"RPCError при обновлении статуса: {e}")
        except Exception as e:
            logger.error(f"Ошибка в keep_online_task: {e}")
        await asyncio.sleep(KEEPONLINE_INTERVAL)

#------ Auto Read ----------
@events.register(events.NewMessage(incoming=True, func=lambda x: not x.via_bot and not x.is_channel))
async def auto_mark_read(event):
    if not is_day():
        return
    if await should_exclude(event):
        return
    
    sender = await event.get_sender()
    username = sender.username if sender and sender.username else None
    msg_type = get_message_types(event.message)
    
    try:
        await event.mark_read()
        logger.info(
            f"\n"
            f"\nПрочитано: (@{username}) -> {event.chat_id} \n"
            f"Message Id: {event.message.id} \n"
            f"Message Type: {msg_type.name.capitalize()} \n"
            f"--------------------------------------------"
        )
    except FloodWaitError as e:
        logger.warning(f"FloodWaitError при чтении, ожидание {e.seconds} секунд")
        await asyncio.sleep(e.seconds + 1)
    except Exception as e:
        logger.error(f"Ошибка при пометке сообщения: {e}")
#---------------------------

async def main():
    global stop_request
    stop_request = False
    
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    client.add_event_handler(auto_mark_read, events.NewMessage)
    
    try:
        await client.start()
        user = await client.get_me()
        logger.info(f"Клиент запущен: ID {user.id}, username @{user.username}")
        try:
            await client(functions.account.UpdateStatusRequest(offline=False))
            logger.debug("Начальный статус установлен: online")
        except Exception as e:
            logger.error(f"Ошибка при установке начального статуса: {e}")
        
        asyncio.create_task(keep_online_task(client))
        await client.run_until_disconnected()
        
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем")
        stop_request = True
    except Exception as e:
        logger.error(f"Ошибка в main: {e}")
    finally:
        try:
            if client.is_connected():
                await client(functions.account.UpdateStatusRequest(offline=True))
                logger.debug("Статус установлен: offline")
        except Exception as e:
            logger.error(f"Ошибка при установке статуса offline: {e}")
        await client.disconnect()
        logger.info("Клиент отключен")

if __name__ == '__main__':
    asyncio.run(main())