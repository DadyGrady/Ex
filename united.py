from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ChatMemberHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
)
import datetime
import uuid
import logging
import os
import json
import emoji
from py3xui import Api, Client, Inbound
from telegram.error import (
    BadRequest,
    Forbidden,
    NetworkError,
    TimedOut,
    TelegramError,
)
from telegram.constants import ParseMode
import asyncio

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Настройки ЮKassa
PROVIDER_TOKEN = '390540012:LIVE:66312'  # Боевой токен
CHANNEL_ID = -1002351837700

# Класс для работы с 3x-ui через py3xui SDK
class X3UI:
    def __init__(self):
        self.host = "http://38.180.231.73:34421/pZDsE0TOSvHl45G/"
        self.username = "Y8NTRap3OH"
        self.password = "bxKcpqyD9b"
        self.token = ""
        self.api = Api(self.host, self.username, self.password, self.token)
        self.login()

    def login(self):
        try:
            self.api.login()
            logger.info("Успешная авторизация на сервере 3x-ui")
        except Exception as e:
            logger.error(f"Ошибка авторизации на сервере 3x-ui: {str(e)}")
            raise Exception(f"Ошибка подключения к серверу 3x-ui: {str(e)}")

    def get_client_list(self):
        try:
            inbounds = self.api.inbound.get_list()
            return inbounds
        except Exception as e:
            logger.error(f"Ошибка получения списка клиентов 3x-ui: {str(e)}")
            raise Exception(f"Ошибка получения списка клиентов 3x-ui: {str(e)}")

    def add_client(self, days, tg_id, user_id, username=None, referral_bonus=0, context=None):
        try:
            client_id = str(uuid.uuid4())
            email = username if username and username.strip() else str(user_id)
            new_client = Client(
                id=client_id,
                email=email,
                enable=True,
                expiry_time=self._calculate_expiry_time(days + referral_bonus),
                total_gb=0,
                limit_ip=3,
                tg_id=str(tg_id),
                alter_id=90,
                flow="xtls-rprx-vision"
            )
            inbound_id = 1
            self.api.client.add(inbound_id, [new_client])
            logger.info(f"Клиент {email} успешно добавлен с подпиской на {days + referral_bonus} дней и flow xtls-rprx-vision")
            if context and context.user_data.get('referral_id'):
                self.update_referral_stats(context.user_data['referral_id'], user_id)
            return client_id, email
        except Exception as e:
            logger.error(f"Ошибка добавления клиента в 3x-ui: {str(e)}")
            raise Exception(f"Ошибка добавления клиента: {str(e)}")

    def extend_subscription(self, user_id, username=None, days=0):
        try:
            email = username if username and username.strip() else str(user_id)
            status = self.get_client_status(user_id, username)
            if status['activ'] != 'Активен':
                raise Exception("У вас нет активной подписки для продления")
            current_expiry = datetime.datetime.strptime(status['time'], '%d.%m.%Y', tzinfo=datetime.timezone.utc)
            new_expiry = current_expiry + datetime.timedelta(days=days)
            inbounds = self.get_client_list()
            for inbound in inbounds:
                for client in inbound.settings.clients:
                    if client.email == email:
                        client.expiry_time = int((new_expiry - datetime.datetime.fromtimestamp(0, datetime.timezone.utc)).total_seconds() * 1000.0)
                        self.api.client.update(client.id, client)
                        break
            logger.info(f"Подписка для {email} продлена на {days} дней")
            return self.get_client_status(user_id, username)
        except Exception as e:
            logger.error(f"Ошибка продления подписки: {str(e)}")
            raise Exception(f"Ошибка продления подписки: {str(e)}")

    def _calculate_expiry_time(self, days):
        now = datetime.datetime.now(datetime.timezone.utc)
        expiry = now + datetime.timedelta(days=days)
        epoch = datetime.datetime.fromtimestamp(0, datetime.timezone.utc)
        x_time = int((expiry - epoch).total_seconds() * 1000.0)
        logger.debug(f"Вычисленное время истечения (мс, UTC): {x_time} для {days} дней")
        return x_time

    def get_client_status(self, user_id, username=None):
        try:
            email = username if username and username.strip() else str(user_id)
            inbounds = self.get_client_list()
            for inbound in inbounds:
                for client in inbound.settings.clients:
                    if client.email == email:
                        now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
                        logger.debug(f"Текущее время (мс, UTC): {now_ms}, Исходное expiry_time: {client.expiry_time}")
                        
                        if client.expiry_time is None or client.expiry_time <= 0:
                            logger.warning(f"Некорректное значение expiry_time для клиента {email}: {client.expiry_time}")
                            return {'activ': 'Не Активен', 'time': '-', 'location': 'Netherlands'}
                        
                        adjusted_expiry = client.expiry_time
                        if client.expiry_time < now_ms:
                            adjusted_expiry += 10800000  # +3 часа
                            logger.debug(f"Попытка корректировки времени истечения на +3 часа (мс): {adjusted_expiry}")
                        if adjusted_expiry <= now_ms:
                            adjusted_expiry += 10800000  # ещё +3 часа
                            logger.debug(f"Попытка дополнительной корректировки на +6 часов (мс): {adjusted_expiry}")
                        
                        if client.enable and adjusted_expiry > now_ms:
                            expiry_time = datetime.datetime.fromtimestamp(adjusted_expiry / 1000, datetime.timezone.utc)
                            logger.debug(f"Подписка активна, истекает: {expiry_time}")
                            return {
                                'activ': 'Активен', 
                                'time': expiry_time.strftime('%d.%m.%Y'), 
                                'location': 'Netherlands'
                            }
                        else:
                            logger.debug(f"Подписка неактивна, adjusted_expiry: {adjusted_expiry}, now_ms: {now_ms}")
                            return {'activ': 'Не Активен', 'time': '-', 'location': 'Netherlands'}
        
            logger.debug(f"Клиент {email} не зарегистрирован")
            return {'activ': 'Не зарегистрирован', 'time': '-', 'location': 'Netherlands'}
        except Exception as e:
            logger.error(f"Ошибка проверки статуса клиента 3x-ui: {str(e)}")
            raise Exception(f"Ошибка проверки статуса: {str(e)}")

    def get_connection_link(self, user_id, username=None, client_id=None):
        try:
            email = username if username and username.strip() else str(user_id)
            if not client_id:
                inbounds = self.get_client_list()
                user_uuid = next((client.id for inbound in inbounds for client in inbound.settings.clients if client.email == email), None)
                if not user_uuid:
                    raise Exception("Клиент не найден")
            else:
                user_uuid = client_id
            inbound = self.get_client_list()[0]
            return self._generate_connection_string(inbound, user_uuid, email)
        except Exception as e:
            logger.error(f"Ошибка получения VLESS-ссылки: {str(e)}")
            raise Exception(f"Ошибка получения ссылки: {str(e)}")

    def _generate_connection_string(self, inbound: Inbound, user_uuid: str, user_email: str) -> str:
        try:
            public_key = inbound.stream_settings.reality_settings.get("settings", {}).get("publicKey")
            server_names = inbound.stream_settings.reality_settings.get("serverNames", [])
            short_ids = inbound.stream_settings.reality_settings.get("shortIds", [])
            if not public_key or not server_names or not short_ids:
                raise Exception("Не удалось извлечь настройки Reality из inbound")
            website_name = server_names[0]
            short_id = short_ids[0]
            connection_string = (
                f"vless://{user_uuid}@38.180.231.73:443"
                f"?type=tcp&security=reality&pbk={public_key}&fp=chrome&sni={website_name}"
                f"&sid={short_id}&spx=%2F&flow=xtls-rprx-vision#VPN-X3-{user_email}"
            )
            return connection_string
        except Exception as e:
            logger.error(f"Ошибка генерации VLESS-ссылки: {str(e)}")
            raise Exception(f"Ошибка генерации строки подключения: {str(e)}")

    def is_user_registered(self, user_id, username=None):
        try:
            return self.get_client_status(user_id, username)['activ'] != 'Не зарегистрирован'
        except Exception as e:
            logger.error(f"Ошибка проверки регистрации пользователя: {str(e)}")
            return False

    def has_active_subscription(self, user_id, username=None):
        return self.get_client_status(user_id, username)['activ'] == 'Активен'

    def update_referral_stats(self, referrer_id, referred_id):
        try:
            referrals_data = self.load_referrals()
            referrer_data = referrals_data.get(str(referrer_id), {"referred": 0, "bonus_days": 0})
            referrer_data["referred"] += 1
            referrer_data["bonus_days"] += 10  # +10 дней за каждого приглашенного
            referrals_data[str(referrer_id)] = referrer_data
            self.save_referrals(referrals_data)
            logger.info(f"Рефералу {referrer_id} добавлено 10 бонусных дней за приглашение {referred_id}")
        except Exception as e:
            logger.error(f"Ошибка обновления реферальной статистики: {str(e)}")

    def get_referral_stats(self, user_id):
        try:
            referrals_data = self.load_referrals()
            return referrals_data.get(str(user_id), {"referred": 0, "bonus_days": 0})
        except Exception as e:
            logger.error(f"Ошибка получения реферальной статистики: {str(e)}")
            return {"referred": 0, "bonus_days": 0}

    def load_referrals(self):
        try:
            if os.path.exists("referrals.json"):
                with open("referrals.json", "r", encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Ошибка загрузки файла referrals.json: {str(e)}")
            return {}

    def save_referrals(self, data):
        try:
            with open("referrals.json", "w", encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Ошибка сохранения файла referrals.json: {str(e)}")

# Инициализация VPN-сервера
vpn = X3UI()

# Клавиатуры
def get_initial_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{emoji.emojize(':star:')} Купить VPN", callback_data="buy_vpn")],
        [InlineKeyboardButton(f"{emoji.emojize(':spiral_notepad:')} Мой VPN", callback_data="my_vpn")],
        [InlineKeyboardButton(f"{emoji.emojize(':busts_in_silhouette:')} Реферальная программа", callback_data="referral_program")],
        [InlineKeyboardButton("Как подключиться к VPN", url="https://telegra.ph/Kak-podklyuchitsya-k-ExVPN-02-27")],
        [InlineKeyboardButton("Поддержка", url="https://t.me/ExVPN_support")]
    ])

def get_channel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Подписаться на канал", url="https://t.me/ExVPN_news")],
        [InlineKeyboardButton("Проверить подписку", callback_data="check_subscription")]
    ])

def get_post_subscription_keyboard(user_id):
    stats = vpn.get_referral_stats(user_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{emoji.emojize(':sparkles:')} Получить реферальную ссылку", callback_data="get_referral_link")],
        [InlineKeyboardButton(f"{emoji.emojize(':bar_chart:')} Реферальная статистика", callback_data="referral_stats")],
        [InlineKeyboardButton("Вывести бонусные дни", callback_data="withdraw_bonus")],
        [InlineKeyboardButton("Назад", callback_data="back_to_initial")]
    ])

def get_tariffs_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"99р | 1 месяц {emoji.emojize(':star:')}", callback_data="buy_30")],
        [InlineKeyboardButton(f"285р (-5%) | 3 месяца {emoji.emojize(':fire:')}", callback_data="buy_90")],
        [InlineKeyboardButton(f"558р (-7%) | 6 месяцев {emoji.emojize(':gem_stone:')}", callback_data="buy_180")],
        [InlineKeyboardButton(f"1080р (-10%) | 12 месяцев {emoji.emojize(':rocket:')}", callback_data="buy_360")],
        [InlineKeyboardButton("Назад", callback_data="back_to_initial")]
    ])

async def get_my_vpn_keyboard(user_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        is_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        if is_member.status not in ['member', 'administrator', 'creator']:
            return InlineKeyboardMarkup([
                [InlineKeyboardButton("Подписаться на канал", url="https://t.me/ExVPN_news")],
                [InlineKeyboardButton("Проверить подписку", callback_data="check_subscription")]
            ])
    except (BadRequest, Forbidden, NetworkError, TimedOut) as e:
        logger.error(f"Ошибка проверки подписки на канал: {str(e)}")
    status = vpn.get_client_status(user_id, None)
    if status['activ'] == 'Не Активен':
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Купить подписку", callback_data="buy_vpn")],
            [InlineKeyboardButton("Назад", callback_data="back_to_initial")]
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Netherlands | до {status['time']}", callback_data="show_vpn_status")],
        [InlineKeyboardButton("Назад", callback_data="back_to_initial")]
    ])

def get_vpn_link_keyboard(link, expiry_date):
    clean_expiry = expiry_date.replace(".", "-")[:32]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Продлить подписку", callback_data=f"extend_subscription_{clean_expiry}")],
        [InlineKeyboardButton("Назад", callback_data="back_to_my_vpn")]
    ])

# Обработчики
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = str(user.id)
    username = user.username
    try:
        is_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
    except (BadRequest, Forbidden, NetworkError, TimedOut) as e:
        logger.error(f"Ошибка проверки подписки на канал: {str(e)}")
        await update.message.reply_text("Ошибка при проверки подписки на канал.")
        return
    referral_arg = context.args[0] if context.args and context.args[0].startswith("referral_") else None
    if referral_arg:
        referrer_id = referral_arg.split("referral_")[1]
        context.user_data['referral_id'] = referrer_id
    if is_member and is_member.status in ['member', 'administrator', 'creator']:
        await update.message.reply_text(
            "Привет! Я бот для продажи услуг подключения к VPN.\nВыберите действие:",
            reply_markup=get_initial_keyboard()
        )
    else:
        await update.message.reply_text(
            "Привет! Для использования сервиса подпишитесь на наш канал:",
            reply_markup=get_channel_keyboard()
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = str(user.id)
    try:
        is_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        if is_member.status in ['member', 'administrator', 'creator']:
            await update.message.reply_text(
                "Привет! Я бот для продажи услуг подключения к VPN.\nВыберите действие:",
                reply_markup=get_initial_keyboard()
            )
        else:
            await update.message.reply_text(
                "Привет! Для использования сервиса подпишитесь на наш канал:",
                reply_markup=get_channel_keyboard()
            )
    except (BadRequest, Forbidden, NetworkError, TimedOut) as e:
        logger.error(f"Ошибка проверки подписки на канал: {str(e)}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    payload = query.invoice_payload
    logger.debug(f"Precheckout query: {query.to_dict()}")
    try:
        days = int(payload.split('_')[1])  # Например, "buy_30"
        user_id = query.from_user.id
        if days in [30, 90, 180, 360]:
            await query.answer(ok=True)
        else:
            await query.answer(ok=False, error_message="Неверный тариф")
    except Exception as e:
        logger.error(f"Ошибка pre_checkout: {str(e)}")
        await query.answer(ok=False, error_message=f"Ошибка обработки платежа: {str(e)}")

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = str(user.id)
    username = user.username
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    logger.debug(f"Successful payment: {payment.to_dict()}")
    days = int(payload.split('_')[1])
    
    status_info = vpn.get_client_status(user_id, username)
    if status_info['activ'] in ['Не Активен', 'Не зарегистрирован']:
        tg_id = str(user.id)
        referral_bonus = 0  # Бонус за регистрацию не добавляем здесь
        client_id, email = vpn.add_client(days, tg_id, user_id, username, referral_bonus, context)
        link = vpn.get_connection_link(user_id, username, client_id)
        status_info = vpn.get_client_status(user_id, username)
        mono_link = f"```\n{link}\n```"
        await update.message.reply_text(
            f"Оплата прошла успешно!\nПодписка на {days} дней создана!\nNetherlands | до {status_info['time']}\nVLESS-ссылка:\n{mono_link}",
            reply_markup=get_vpn_link_keyboard(link, status_info['time']),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "У вас уже есть активная подписка. Нельзя купить новую, пока старая активна.",
            reply_markup=await get_my_vpn_keyboard(user_id, context)
        )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_id = str(user.id)
    username = user.username
    data = query.data
    await query.answer()

    logger.debug(f"Обработка callback: {data}, user_id: {user_id}")
    try:
        if data == "back_to_initial":
            is_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
            if is_member.status in ['member', 'administrator', 'creator']:
                await query.edit_message_text("Привет! Выберите действие:", reply_markup=get_initial_keyboard())
            else:
                await query.edit_message_text("Подпишитесь на канал:", reply_markup=get_channel_keyboard())
            return

        if data == "back_to_my_vpn":
            keyboard = await get_my_vpn_keyboard(user_id, context)
            await query.edit_message_text(
                "Управление подпиской:",
                reply_markup=keyboard
            )
            return

        if data == "check_subscription":
            is_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
            if is_member.status in ['member', 'administrator', 'creator']:
                await query.edit_message_text("Спасибо за подписку! Выберите действие:", reply_markup=get_initial_keyboard())
            else:
                await query.edit_message_text("Вы еще не подписаны на канал:", reply_markup=get_channel_keyboard())
            return

        if data == "buy_vpn":
            is_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
            if is_member.status not in ['member', 'administrator', 'creator']:
                await query.edit_message_text("Подпишитесь на канал:", reply_markup=get_channel_keyboard())
                return
            await query.edit_message_text("Выберите тариф:", reply_markup=get_tariffs_keyboard())
            return

        if data == "my_vpn":
            is_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
            if is_member.status not in ['member', 'administrator', 'creator']:
                await query.edit_message_text("Подпишитесь на канал:", reply_markup=get_channel_keyboard())
                return
            keyboard = await get_my_vpn_keyboard(user_id, context)
            await query.edit_message_text(
                "Управление подпиской:",
                reply_markup=keyboard
            )
            return

        if data == "show_vpn_status":
            status_info = vpn.get_client_status(user_id, username)
            if status_info['activ'] == 'Активен':
                expiry_date = status_info['time']
                link = vpn.get_connection_link(user_id, username)
                mono_link = f"```\n{link}\n```"
                await query.edit_message_text(
                    f"Вот ваша ссылка\nДо {expiry_date}\nVLESS-ссылка:\n{mono_link}",
                    reply_markup=get_vpn_link_keyboard(link, expiry_date),
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text(
                    "Ваша подписка истекла. Купите подписку.",
                    reply_markup=await get_my_vpn_keyboard(user_id, context)
                )
            return

        if data == "referral_program":
            is_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
            if is_member.status not in ['member', 'administrator', 'creator']:
                await query.edit_message_text("Подпишитесь на канал:", reply_markup=get_channel_keyboard())
                return
            await query.edit_message_text(
                "Реферальная программа:\nПриглашай друзей и получай бонусные дни!",
                reply_markup=get_post_subscription_keyboard(user_id)
            )
            return

        if data == "get_referral_link":
            referral_link = f"https://t.me/ExVPN1bot?start=referral_{user_id}"
            await query.edit_message_text(
                f"Ваша реферальная ссылка:\n{referral_link}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Назад", callback_data="referral_program")]
                ])
            )
            return

        if data == "referral_stats":
            stats = vpn.get_referral_stats(user_id)
            await query.edit_message_text(
                f"Реферальная статистика:\nПриглашено друзей: {stats['referred']}\nБонусные дни: {stats['bonus_days']}",
                reply_markup=get_post_subscription_keyboard(user_id)
            )
            return

        if data == "withdraw_bonus":
            stats = vpn.get_referral_stats(user_id)
            if stats['bonus_days'] > 0 and vpn.has_active_subscription(user_id, username):
                status = vpn.get_client_status(user_id, username)
                current_expiry = datetime.datetime.strptime(status['time'], '%d.%m.%Y', tzinfo=datetime.timezone.utc)
                new_expiry = current_expiry + datetime.timedelta(days=stats['bonus_days'])
                email = username if username and username.strip() else str(user_id)
                inbounds = vpn.get_client_list()
                for inbound in inbounds:
                    for client in inbound.settings.clients:
                        if client.email == email:
                            client.expiry_time = int((new_expiry - datetime.datetime.fromtimestamp(0, datetime.timezone.utc)).total_seconds() * 1000.0)
                            vpn.api.client.update(client.id, client)
                            break
                referrals_data = vpn.load_referrals()
                referrals_data[str(user_id)]["bonus_days"] = 0  # Сбрасываем бонусные дни
                vpn.save_referrals(referrals_data)
                await query.edit_message_text(
                    f"Бонусные дни выведены!\nNetherlands | до {new_expiry.strftime('%d.%m.%Y')}",
                    reply_markup=get_post_subscription_keyboard(user_id)
                )
            else:
                await query.edit_message_text(
                    "Нет бонусных дней или активной подписки для вывода.",
                    reply_markup=get_post_subscription_keyboard(user_id)
                )
            return

        tariffs = {
            "buy_30": {"days": 30, "amount": 99},
            "buy_90": {"days": 90, "amount": 285},
            "buy_180": {"days": 180, "amount": 558},
            "buy_360": {"days": 360, "amount": 1080},
        }
        if data in tariffs:
            tariff = tariffs[data]
            days = tariff["days"]
            amount = tariff["amount"]
            status_info = vpn.get_client_status(user_id, username)
            if status_info['activ'] in ['Не Активен', 'Не зарегистрирован']:
                logger.debug(f"Отправка инвойса: user_id={user_id}, days={days}, amount={amount}")
                await context.bot.send_invoice(
                    chat_id=user_id,
                    title=f"VPN на {days} дней",
                    description=f"Подписка на VPN на {days} дней",
                    payload=f"buy_{days}",
                    provider_token=PROVIDER_TOKEN,
                    currency="RUB",
                    prices=[{"label": "Подписка", "amount": int(amount * 100)}],  # Сумма в копейках
                    start_parameter=f"buy_{days}",
                    need_email=True,  # Запрашиваем email для чека
                    send_email_to_provider=True,  # Отправляем email в YooKassa
                    provider_data={
                        "receipt": {
                            "items": [
                                {
                                    "description": f"Подписка на VPN на {days} дней",
                                    "quantity": "1",
                                    "amount": {
                                        "value": f"{amount}.00",
                                        "currency": "RUB"
                                    },
                                    "vat_code": 1
                                }
                            ]
                        }
                    }
                )
            else:
                await query.edit_message_text(
                    "У вас уже есть активная подписка. Нельзя купить новую, пока старая активна.",
                    reply_markup=await get_my_vpn_keyboard(user_id, context)
                )

        if data.startswith("extend_subscription_"):
            expiry_date = data.replace("extend_subscription_", "").replace("-", ".")
            await query.edit_message_text("На сколько дней продлить подписку?", reply_markup=get_tariffs_keyboard())
            context.user_data['extend_expiry_date'] = expiry_date
            return

    except TelegramError as e:
        logger.error(f"Ошибка Telegram API в обработке callback {data}: {str(e)}")
        await query.edit_message_text(f"Произошла ошибка: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка в обработке callback {data}: {str(e)}")
        await query.edit_message_text(f"Произошла ошибка: {str(e)}")

async def check_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    current_time = datetime.datetime.now(datetime.timezone.utc)
    users = context.bot_data.get('users', set())
    for user_id in users:
        status = vpn.get_client_status(str(user_id))
        if status['activ'] == 'Активен':
            expiry = datetime.datetime.strptime(status['time'], '%d.%m.%Y', tzinfo=datetime.timezone.utc)
            if (expiry - current_time).days <= 1:
                if not context.user_data.get(f'subscription_warning_{user_id}', False):
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"⚠️ Ваша подписка истекает {expiry.strftime('%d.%m.%Y')}. Продлите её через /start -> Мой VPN."
                    )
                    context.user_data[f'subscription_warning_{user_id}'] = True
                    logger.info(f"Уведомление отправлено пользователю {user_id}")

async def check_channel_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.chat_member.new_chat_member.status in ['member', 'administrator', 'creator']:
            user_id = str(update.chat_member.new_chat_member.user.id)
            context.bot_data.setdefault('users', set()).add(user_id)
            await context.bot.send_message(
                chat_id=user_id,
                text="Спасибо за подписку! Выберите действие:",
                reply_markup=get_initial_keyboard()
            )
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {str(e)}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = str(user.id)
    username = user.username
    status_info = vpn.get_client_status(user_id, username)
    if status_info['activ'] == 'Активен':
        await update.message.reply_text(f"Netherlands | до {status_info['time']}")
    else:
        await update.message.reply_text("У вас нет активной подписки.")

async def get_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = str(user.id)
    username = user.username
    status_info = vpn.get_client_status(user_id, username)
    if status_info['activ'] == 'Активен':
        link = vpn.get_connection_link(user_id, username)
        expiry_date = status_info['time']
        mono_link = f"```\n{link}\n```"
        await update.message.reply_text(f"Netherlands | до {expiry_date}\nVLESS-ссылка:\n{mono_link}", reply_markup=get_vpn_link_keyboard(link, expiry_date), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("У вас нет активной подписки. Купите подписку: /start.")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("Неизвестная команда. Используйте /start.")

async def run_bot():
    application = Application.builder().token("7118899005:AAETG-Z__d4HdUMThgyXhQWEu9fvgZmh9GY").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("link", get_link))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))
    application.add_handler(ChatMemberHandler(check_channel_subscription, chat_id=CHANNEL_ID))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    application.bot_data['users'] = {937985017}
    if application.job_queue is None:
        logger.error("JobQueue не доступен. Установите 'python-telegram-bot[job-queue]'")
        raise RuntimeError("JobQueue не настроен. Установите нужную зависимость.")
    application.job_queue.run_daily(
        check_subscriptions,
        time=datetime.time(hour=9, minute=0, tzinfo=datetime.timezone.utc)
    )
    logger.info("Задача проверки подписок зарегистрирована на 9:00 UTC")

    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES, timeout=10)

    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        logger.info("Остановка бота")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        logger.info("Остановка бота по Ctrl+C")
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
    except Exception as e:
        logger.error(f"Необработанная ошибка: {str(e)}")
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()