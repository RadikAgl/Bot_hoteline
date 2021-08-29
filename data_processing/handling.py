import redis
from telebot.types import Message
from loguru import logger

from translations.translations import vocabulary


steps = {
    '1': 'destination_id',
    '2min': 'min_price',
    '2max': 'max_price',
    '3': 'distance',
    '4': 'quantity',
}
currencies = {
    "ru": "RUB",
    "en": "USD"
}
locales = {
    "ru": "ru_RU",
    "en": "en_US"
}

logger_config = {
    "handlers": [
        {
            "sink": "logs/bot.log",
            "format": "{time} | {level} | {message}",
            "encoding": "utf-8",
            "level": "DEBUG",
            "rotation": "5 MB",
            "compression": "zip"
        },
    ],
}

redis_db = redis.StrictRedis(
    host='localhost',
    port=6379,
    db=1,
    charset='utf-8',
    decode_responses=True
)


def gen_key(msg: Message, additional: str) -> str:
    """
    makes str like key from user id and additional word
    :param msg: Messsage
    :param additional: str additional word
    :return: str str like key for redis
    """
    return str(msg.chat.id) + additional


def internationalize(key: str, msg: Message) -> str:
    """
    takes text in vocabulary in current language with key
    :param key: str key
    :param msg: Message
    :return: text of message from vocabulary
    """
    lang = redis_db.get(gen_key(msg, 'language'))
    return vocabulary[key][lang]


_ = internationalize


def is_input_correct(msg: Message) -> bool:
    """

    Checks the correctness of incoming messages as search parameters
    :param msg: Message
    :return: True if the message text is correct
    """
    state = redis_db.get(gen_key(msg, 'state'))
    msg = msg.text.strip()
    if state == '4' and ' ' not in msg and msg.isdigit() and 0 < int(msg) <= 20:
        return True
    elif state == '3' and ' ' not in msg and msg.replace('.', '').isdigit():
        return True
    elif state == '2' and msg.replace(' ', '').isdigit() and len(msg.split()) == 2:
        return True
    elif state == '1' and msg.replace(' ', '').replace('-', '').isalpha():
        return True


def get_parameters_information(msg: Message) -> str:
    """
    generates a message with information about the current search parameters
    :param msg:
    :return: string like information about search parameters
    """
    logger.info(f'Function {get_parameters_information.__name__} called with argument: {msg}')
    sort_order = redis_db.get(gen_key(msg, 'order'))
    city = redis_db.get(gen_key(msg, 'destination_name'))
    currency = redis_db.get(gen_key(msg, 'currency'))
    message = (
        f"<b>{_('parameters', msg)}</b>\n"
        f"{_('city', msg)}: {city}\n"
    )
    if sort_order == "DISTANCE_FROM_LANDMARK":
        price_min = redis_db.get(gen_key(msg, 'min_price'))
        price_max = redis_db.get(gen_key(msg, 'max_price'))
        distance = redis_db.get(gen_key(msg, 'distance'))
        message += f"{_('price', msg)}: {price_min} - {price_max} {currency}\n" \
                   f"{_('max_distance', msg)}: {distance} {_('dis_unit', msg)}"
    logger.info(f'Search parameters: {message}')
    return message


def make_message(msg: Message, prefix: str) -> str:
    """
    makes and returns messages with information about an invalid input or with question, depending on the prefix and
    state
    :param msg: Message
    :param prefix: prefix for key in vocabulary dictionary
    :return: string like message
    """
    state = redis_db.get(gen_key(msg, 'state'))
    message = _(prefix + state, msg)
    if state == '2':
        message += f" ({redis_db.get(gen_key(msg, 'currency'))})"

    return message


