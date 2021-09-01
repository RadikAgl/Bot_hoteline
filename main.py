import os

import telebot
from telebot.types import Message, CallbackQuery
from dotenv import load_dotenv
from loguru import logger

from botrequests.hotels import get_hotels
from botrequests.locations import exact_location, make_locations_list
from utils.handling import internationalize as _, is_input_correct, get_parameters_information, \
    make_message, steps, locales, logger_config, currencies
from bot_redis import redis_db

logger.configure(**logger_config)
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')


def get_locations(msg: Message) -> None:
    """
    takes location name, searches locations with similar name and sends result to chat
    :param msg: Message
    :return: None
    """
    if not is_input_correct(msg):
        bot.send_message(msg.chat.id, make_message(msg, 'mistake_'))
    else:
        wait_msg = bot.send_message(msg.chat.id, _('wait', msg))
        locations = make_locations_list(msg)
        bot.delete_message(msg.chat.id, wait_msg.id)
        if not locations or len(locations) < 1:
            bot.send_message(msg.chat.id, str(msg.text) + _('locations_not_found', msg))
        elif locations.get('bad_request'):
            bot.send_message(msg.chat.id, _('bad_request', msg))
        else:
            menu = telebot.types.InlineKeyboardMarkup()
            for loc_name, loc_id in locations.items():
                menu.add(telebot.types.InlineKeyboardButton(
                    text=loc_name,
                    callback_data='code' + loc_id)
                )
            menu.add(telebot.types.InlineKeyboardButton(text=_('cancel', msg), callback_data='cancel'))
            bot.send_message(msg.chat.id, _('loc_choose', msg), reply_markup=menu)


@bot.message_handler(commands=['settings'])
def get_command_settings(message: Message) -> None:
    """
    "/settings" command handler, opens settings menu
    :param message: Message
    :return: None
    """
    logger.info(f'Функция {get_command_settings.__name__} вызвана с параметром: {message}')
    menu = telebot.types.InlineKeyboardMarkup()
    menu.add(telebot.types.InlineKeyboardButton(text=_("language_", message), callback_data='set_locale'))
    menu.add(telebot.types.InlineKeyboardButton(text=_("currency_", message), callback_data='set_currency'))
    menu.add(telebot.types.InlineKeyboardButton(text=_("cancel", message), callback_data='cancel'))
    bot.send_message(message.chat.id, _("settings", message), reply_markup=menu)


@bot.message_handler(commands=['lowprice', 'highprice', 'bestdeal'])
def get_searching_commands(message: Message) -> None:
    """
    "/lowprice", "/highprice", "/bestdeal"  commands handler, sets the sort order and starts asking for parameters
    from the user

    :param message: Message
    :return: None
    """
    logger.info("\n" + "=" * 100 + "\n")
    chat_id = message.chat.id
    redis_db.hset(chat_id, 'state', 1)
    if 'lowprice' in message.text:
        redis_db.hset(chat_id, 'order', 'PRICE')
        logger.info('"lowprice" command is called')
    elif 'highprice' in message.text:
        redis_db.hset(chat_id, 'order', 'PRICE_HIGHEST_FIRST')
        logger.info('"highprice" command is called')
    else:
        redis_db.hset(chat_id, 'order', 'DISTANCE_FROM_LANDMARK')
        logger.info('"bestdeal" command is called')
    logger.info(redis_db.hget(chat_id, 'order'))
    state = redis_db.hget(chat_id, 'state')
    logger.info(f"Current state: {state}")
    bot.send_message(chat_id, make_message(message, 'question_'))


@bot.message_handler(commands=['help', 'start'])
def get_command_help(message: Message) -> None:
    """
    "/help" command handler, displays information about bot commands in the chat
    :param message: Message
    :return: None
    """
    if 'start' in message.text:
        logger.info(f'"start" command is called')
        lang = message.from_user.language_code
        if lang != 'ru':
            lang = 'en'
        redis_db.hset(message.chat.id, mapping={
            "language": lang,
            "state": 0,
            "locale": locales[lang],
            "currency": currencies[lang]
        })

        bot.send_message(message.chat.id, _('hello', message))
    else:
        logger.info(f'"help" command is called')
        bot.send_message(message.chat.id, _('help', message))


@bot.callback_query_handler(func=lambda call: True)
def keyboard_handler(call: CallbackQuery) -> None:
    """
    buttons handlers
    :param call: CallbackQuery
    :return: None
    """
    logger.info(f'Function {keyboard_handler.__name__} called with argument: {call}')
    chat_id = call.message.chat.id
    bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id)

    if call.data.startswith('code'):
        loc_name = exact_location(call.message.json, call.data)
        redis_db.hset(chat_id, mapping={"destination_id": call.data[4:], "destination_name": loc_name})
        logger.info(f"{loc_name} selected")
        bot.send_message(
            chat_id,
            f"{_('loc_selected', call.message)}: {loc_name}",
        )
        if redis_db.hget(chat_id, 'order') == 'DISTANCE_FROM_LANDMARK':
            redis_db.hincrby(chat_id, 'state', 1)
        else:
            redis_db.hincrby(chat_id, 'state', 3)
        bot.send_message(chat_id, make_message(call.message, 'question_'))

    elif call.data.startswith('set'):
        redis_db.hset(chat_id, 'state', 0)
        menu = telebot.types.InlineKeyboardMarkup()
        if call.data == 'set_locale':
            logger.info(f'language change menu')
            menu.add(telebot.types.InlineKeyboardButton(text='Русский', callback_data='loc_ru_RU'))
            menu.add(telebot.types.InlineKeyboardButton(text='English', callback_data='loc_en_US'))
        elif call.data == 'set_currency':
            logger.info(f'currency change menu')
            menu.add(telebot.types.InlineKeyboardButton(text='RUB', callback_data='cur_RUB'))
            menu.add(telebot.types.InlineKeyboardButton(text='USD', callback_data='cur_USD'))
            menu.add(telebot.types.InlineKeyboardButton(text='EUR', callback_data='cur_EUR'))
        menu.add(telebot.types.InlineKeyboardButton(text=_('cancel', call.message), callback_data='cancel'))
        bot.send_message(chat_id, _('ask_to_select', call.message), reply_markup=menu)

    elif call.data.startswith('loc'):
        redis_db.hset(chat_id, mapping={"locale": call.data[4:], "language": call.data[4:6]})
        bot.send_message(chat_id, f"{_('current_language', call.message)}: {_('language', call.message)}")
        logger.info(f"Language changed to {redis_db.hget(chat_id, 'language')}")
        logger.info(f"Locale changed to {redis_db.hget(chat_id, 'locale')}")

    elif call.data.startswith('cur'):
        redis_db.hset(chat_id, 'currency', call.data[4:])
        bot.send_message(chat_id, f"{_('current_currency', call.message)}: {call.data[4:]}")
        logger.info(f"Currency changed to {redis_db.hget(chat_id, 'currency')}")

    elif call.data == 'cancel':
        logger.info(f'Canceled by user')
        redis_db.hset(chat_id, 'state', 0)
        bot.send_message(chat_id, _('canceled', call.message))


def get_search_parameters(msg: Message) -> None:
    """
    fixes search parameters
    :param msg: Message
    :return: None
    """
    logger.info(f'Function {get_command_settings.__name__} called with argument: {msg}')
    chat_id = msg.chat.id
    state = redis_db.hget(chat_id, 'state')
    if not is_input_correct(msg):
        bot.send_message(chat_id, make_message(msg, 'mistake_'))
    else:
        redis_db.hincrby(msg.chat.id, 'state', 1)
        if state == '2':
            min_price, max_price = sorted(msg.text.strip().split(), key=int)
            redis_db.hset(chat_id, steps[state + 'min'], min_price)
            logger.info(f"{steps[state + 'min']} set to {min_price}")
            redis_db.hset(chat_id, steps[state + 'max'], max_price)
            logger.info(f"{steps[state + 'max']} set to {max_price}")
            bot.send_message(chat_id, make_message(msg, 'question_'))
        elif state == '4':
            redis_db.hset(chat_id, steps[state], msg.text.strip())
            logger.info(f"{steps[state]} set to {msg.text.strip()}")
            redis_db.hset(chat_id, 'state', 0)
            hotels_list(msg)
        else:
            redis_db.hset(chat_id, steps[state], msg.text.strip())
            logger.info(f"{steps[state]} set to {msg.text.strip()}")
            bot.send_message(chat_id, make_message(msg, 'question_'))


def hotels_list(msg: Message) -> None:
    """
    displays hotel search results in chat
    :param msg: Message
    :return: None
    """
    chat_id = msg.chat.id
    wait_msg = bot.send_message(chat_id, _('wait', msg))
    hotels = get_hotels(msg)
    logger.info(f'Function {get_hotels.__name__} returned: {hotels}')
    bot.delete_message(chat_id, wait_msg.id)
    if not hotels or len(hotels) < 1:
        bot.send_message(chat_id, _('hotels_not_found', msg))
    elif 'bad_request' in hotels:
        bot.send_message(chat_id, _('bad_request', msg))
    else:
        quantity = len(hotels)
        bot.send_message(chat_id, get_parameters_information(msg))
        bot.send_message(chat_id, f"{_('hotels_found', msg)}: {quantity}")
        for hotel in hotels:
            bot.send_message(chat_id, hotel)


@bot.message_handler(content_types=['text'])
def get_text_messages(message) -> None:
    """
    text messages handler
    :param message: Message
    :return: None
    """
    state = redis_db.hget(message.chat.id, 'state')
    logger.info(f"{state} - {type(state)}")
    if state == '1':
        get_locations(message)
    elif state in ['2', '3', '4']:
        get_search_parameters(message)
    else:
        bot.send_message(message.chat.id, _('misunderstanding', message))


try:
    bot.polling(none_stop=True, interval=0)
except Exception as e:
    logger.opt(exception=True).error(f'Unexpected error: {e}')

