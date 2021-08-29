import os

import requests
from dotenv import load_dotenv
from loguru import logger
from telebot.types import Message

from data_processing.handling import gen_key, check_in_n_out_dates, hotel_price, _, hotel_address, \
    hotel_rating
from bot_redis import redis_db

load_dotenv()

X_RAPIDAPI_KEY = os.getenv('RAPID_API_KEY')


def get_hotels(msg: Message) -> [list, None]:
    """
    calls the required functions to take and process the hotel data
    :param msg: Message
    :return: list with string like hotel descriptions
    """
    data = request_hotels(msg) # json дата из сервера прям голая
    if 'bad_req' in data:
        return ['bad_request']
    data = structure_hotels_info(msg, data)
    if not data or len(data['results']) < 1:
        return None
    if redis_db.get(gen_key(msg, 'order')) == 'DISTANCE_FROM_LANDMARK':
        next_page = data.get('next_page')
        distance = float(redis_db.get(gen_key(msg, 'distance')))
        while next_page and next_page < 5 \
                and float(data['results'][-1]['distance'].replace(',', '.').split()[0]) <= distance:
            add_data = request_hotels(msg, next_page)
            if 'bad_req' in data:
                logger.warning('bad_request')
                break
            add_data = structure_hotels_info(msg, add_data)
            if add_data and len(add_data["results"]) > 0:
                data['results'].extend(add_data['results'])
                next_page = add_data['next_page']
            else:
                break
        quantity = int(redis_db.get(gen_key(msg, 'quantity')))
        data = choose_best_hotels(data['results'], distance, quantity)
    else:
        data = data['results']

    data = generate_hotels_descriptions(data, msg)
    return data


def request_hotels(msg, page: int = 1):
    """
    request information from the hotel api
    :param msg: Message
    :param page: page number
    :return: response from hotel api
    """
    logger.info(f'Function {request_hotels.__name__} called with argument: page = {page}, msg = {msg}')

    url = "https://hotels4.p.rapidapi.com/properties/list"
    dates = check_in_n_out_dates()

    querystring = {
        "adults1": "1",
        "pageNumber": page,
        "destinationId": redis_db.get(gen_key(msg, 'destination_id')),
        "pageSize": redis_db.get(gen_key(msg, 'quantity')),
        "checkOut": dates['check_out'],
        "checkIn": dates['check_in'],
        "sortOrder": redis_db.get(gen_key(msg, 'order')),
        "locale": redis_db.get(gen_key(msg, 'locale')),
        "currency": redis_db.get(gen_key(msg, 'currency'))
    }
    if redis_db.get(gen_key(msg, 'order')) == 'DISTANCE_FROM_LANDMARK':
        querystring['priceMax'] = redis_db.get(gen_key(msg, 'max_price'))
        querystring['priceMin'] = redis_db.get(gen_key(msg, 'min_price'))
        querystring['pageSize'] = '25'

    logger.info(f'Search parameters: {querystring}')

    headers = {
        'x-rapidapi-key': X_RAPIDAPI_KEY,
        'x-rapidapi-host': "hotels4.p.rapidapi.com"
    }

    try:
        response = requests.request("GET", url, headers=headers, params=querystring)
        data = response.json()
        if data.get('message'):
            raise requests.exceptions.RequestException

        logger.info(f'Hotels api(properties/list) response received: {data}')
        return data

    except requests.exceptions.RequestException as e:
        logger.error(f'Error receiving response: {e}')
        return {'bad_req': 'bad_req'}
    except Exception as e:
        logger.info(f'Error in function {request_hotels.__name__}: {e}')


def structure_hotels_info(msg: Message, data: dict) -> dict:
    """
    structures hotel data
    :param msg: Message
    :param data: hotel data
    :return: dict of structured hotel data
    """
    logger.info(f'Function {structure_hotels_info.__name__} called with argument: msd = {msg}, data = {data}')
    data = data.get('data', {}).get('body', {}).get('searchResults')
    hotels = dict()
    hotels['total_count'] = data.get('totalCount', 0)

    logger.info(f"Next page: {data.get('pagination', {}).get('nextPageNumber', 0)}")
    hotels['next_page'] = data.get('pagination', {}).get('nextPageNumber')
    hotels['results'] = []

    try:
        if hotels['total_count'] > 0:
            for cur_hotel in data.get('results'):
                hotel = dict()
                hotel['name'] = cur_hotel.get('name')
                hotel['star_rating'] = cur_hotel.get('starRating', 0)
                hotel['price'] = hotel_price(cur_hotel)
                if not hotel['price']:
                    continue
                hotel['distance'] = cur_hotel.get('landmarks')[0].get('distance', _('no_information', msg))
                hotel['address'] = hotel_address(cur_hotel, msg)

                if hotel not in hotels['results']:
                    hotels['results'].append(hotel)
        logger.info(f'Hotels in function {structure_hotels_info.__name__}: {hotels}')
        return hotels

    except Exception as e:
        logger.info(f'Error in function {structure_hotels_info.__name__}: {e}')


def choose_best_hotels(hotels: list[dict], distance: float, limit: int) -> list[dict]:
    """
    deletes hotels that have a greater distance from the city center than the specified one, sorts the rest by price in order
    increasing and limiting the selection
    :param limit: number of hotels
    :param distance: maximum distance from city center
    :param hotels: structured hotels data
    :return: required number of best hotels
    """
    logger.info(f'Function {choose_best_hotels.__name__} called with arguments: '
                f'distance = {distance}, quantity = {limit}\n{hotels}')
    hotels = list(filter(lambda x: float(x["distance"].strip().replace(',', '.').split()[0]) <= distance, hotels))
    logger.info(f'Hotels filtered: {hotels}')
    hotels = sorted(hotels, key=lambda k: k["price"])
    logger.info(f'Hotels sorted: {hotels}')
    if len(hotels) > limit:
        hotels = hotels[:limit]
    return hotels


def generate_hotels_descriptions(hotels: dict, msg: Message) -> list[str]:
    """
    generate hotels description
    :param msg: Message
    :param hotels: Hotels information
    :return: list with string like hotel descriptions
    """
    logger.info(f'Function {generate_hotels_descriptions.__name__} called with argument {hotels}')
    hotels_info = []

    for hotel in hotels:
        message = (
            f"{_('hotel', msg)}: {hotel.get('name')}\n"
            f"{_('rating', msg)}: {hotel_rating(hotel.get('star_rating'), msg)}\n"
            f"{_('price', msg)}: {hotel['price']} {redis_db.get(gen_key(msg, 'currency'))}\n"
            f"{_('distance', msg)}: {hotel.get('distance')}\n"
            f"{_('address', msg)}: {hotel.get('address')}\n"
        )
        hotels_info.append(message)
    return hotels_info
