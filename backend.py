import os
import logging
from wit import Wit
import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from enum import Enum
from time import sleep

wit_access_token = os.environ.get('wit_access_token')
telegram_access_token = os.environ.get('telegram_access_token')

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)


class Pizza:
    def __init__(self, name, ingredients):
        self.name = name
        self.ingredients = ingredients

    def __str__(self):
        return '{} ({})'.format(self.name, ', '.join(self.ingredients))

    def __eq__(self, other):
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)

    def with_ingredient(self, ingredient):
        return ingredient in self.ingredients


class Order:
    def __init__(self):
        self.order = {
            Pizza('margherita', ['mozarella', 'tomato sauce']): 0,
            Pizza('pepperoni', ['mozarella', 'pepperoni', 'tomato sauce']): 0,
            Pizza('champignon', ['mozarella', 'mushrooms', 'onions', 'tomato sauce']): 0,
            Pizza('veggie', ['spinach', 'corn', 'tomato sauce']): 0,
            Pizza('tuna', ['mozarella', 'tuna', 'onion', 'tomato sauce']): 0,
        }

    def __str__(self):
        order = '\n'.join(['- {} {}'.format(value, key)
                           for key, value in self.order.items() if value != 0])
        if order != '':
            return order
        else:
            return ['No order was placed.']

    def add_pizza(self, pizza, amount):
        self.order[pizza] += amount


class Address:
    def __init__(self):
        self.name = ''
        self.street_name = ''
        self.street_nr = ''
        self.city = ''
        self.code = ''

    def __str__(self):
        return 'Delivery address: {}, {} {}, {}, {}'.format(self.name, self.street_name, self.street_nr, self.code, self.city)

    def add_name(self, name):
        self.name = name

    def add_street(self, street_name, street_nr):
        self.street_name = street_name
        self.street_nr = street_nr

    def add_city(self, city):
        self.city = city

    def add_code(self, code):
        self.code = code


class Entity(Enum):
    GREETINGS = 'greetings'
    INTENT_ORDER = 'intent_order'
    INTENT_MENU = 'intent_menu'
    PIZZA_TYPE = 'pizza_type'
    PIZZA_INGREDIENT = 'pizza_ingredient'
    LOCATION = 'location'
    OPTIONS = 'options'
    BYE = 'bye'
    INTENT_NO = 'intent_no'
    INTENT_YES = 'intent_yes'
    INTENT_INGREDIENT = 'intent_ingredient'
    CONTACT = 'contact'
    CITY = 'city'
    STREET_NAME = 'street_name'
    STREET_NUMBER = 'street_number'
    INTENT_WRONG = 'intent_wrong'
    NUMBER = 'number'


class State(Enum):
    GREETINGS = 'greetings',
    ORDER = 'order',
    ADDRESS = 'address',
    ADDRESS_NAME = 'address_name',
    ADDRESS_CITY = 'address_city',
    ADDRESS_CODE = 'address_code',
    ADDRESS_STREET = 'address_street',
    CORRECTION = 'correction',
    SUMMARY = 'summary',


menu = {
    'margherita': Pizza('margherita', ['mozarella', 'tomato sauce']),
    'pepperoni': Pizza('pepperoni', ['mozarella', 'pepperoni', 'tomato sauce']),
    'champignon': Pizza('champignon', ['mozarella', 'mushrooms', 'onions', 'tomato sauce']),
    'veggie': Pizza('veggie', ['spinach', 'corn', 'tomato sauce']),
    'tuna': Pizza('tuna', ['mozarella', 'tuna', 'onion', 'tomato sauce']),
}

conversation_states = {
    'greetings': False,
    'order': False,
    'address': False,
    'address_name': False,
    'address_city': False,
    'address_code': False,
    'address_street': False,
    'summary': False,
}


state = State.GREETINGS
order = Order()
address = Address()


def parse_response(response):
    global state
    global order
    global address

    entities = response['entities']
    for entity in entities:
        if entity == Entity.GREETINGS.value:
            state = State.ORDER
            return say_hello()
        elif entity == Entity.INTENT_MENU.value:
            state = State.ORDER
            return get_menu()
        elif entity == Entity.INTENT_INGREDIENT.value:
            state = State.ORDER
            ingredient = entities['pizza_ingredient'][0]['value']
            return get_menu(ingredient)
        elif entity == Entity.INTENT_ORDER.value:
            state = State.ORDER
            return get_order(entities)
        elif entity == Entity.INTENT_NO.value and state == State.ORDER:
            state = State.ADDRESS
            return say_address_name()
        elif entity == Entity.CONTACT.value and state == State.ADDRESS:
            state = State.ADDRESS_NAME
            address.add_name(entities['contact'][0]['value'].capitalize())
            return say_address_city()
        elif entity == Entity.CITY.value and state == State.ADDRESS_NAME:
            state = State.ADDRESS_CITY
            address.add_city(entities['city'][0]['value'].capitalize())
            return say_address_code()
        elif entity == Entity.NUMBER.value and state == State.ADDRESS_CITY:
            try:
                code = entities['number'][0]['value']
            except KeyError:
                code = ''
            if check_address_code(code):
                state = State.ADDRESS_CODE
                address.add_code(code)
                return say_address_street()
            else:
                return say_address_code_incorrect()
        elif entity == Entity.STREET_NAME.value and state == State.ADDRESS_CODE:
            try:
                street_name = entities['street_name'][0]['value']
                street_nr = entities['street_number'][0]['value']
            except KeyError:
                return say_address_street_incorrect()
            state = State.ADDRESS_STREET
            address.add_street(street_name, street_nr)
            return say_confirm_address(address.__str__())
        elif entity == Entity.INTENT_NO.value and state == State.ADDRESS_STREET:
            state = State.CORRECTION
            return say_wrong()
        elif entity == Entity.INTENT_YES.value and state == State.ADDRESS_STREET:
            state = State.SUMMARY
            return say_summary()
        elif entity == Entity.INTENT_WRONG.value and state == State.CORRECTION:
            wrong = entities['intent_wrong']
            state = State.SUMMARY
            return ['OK, we do not have time for that! ({})'.format(wrong[0]['value'])] + say_summary()
        elif entity == Entity.BYE.value:
            state = State.GREETINGS
            order = Order()
            address = Address()
            return ['Cancelling order process. Bye!']

    return say_options()


def say_hello():
    return ['Hello!', 'I\'m a bot. You can ask me to show you the menu or order the pizza straight away if you know what you want.']


def get_menu(ingredient='tomato sauce'):
    global menu
    _menu = 'Here is the menu:'
    for pizza in menu.values():
        _menu += '\n- {}'.format(pizza) if pizza.with_ingredient(ingredient) else ''
    return [_menu]


def get_order(entities):
    global menu
    try:
        pizza_amount = entities['pizza_amount']
        pizza_type = entities['pizza_type']
    except KeyError:
        return ['Please specify the amount of each pizza you want.']
    for x in zip(pizza_type, pizza_amount):
        order.add_pizza(menu[x[0]['value']], int(x[1]['value']))
    return [order.__str__(), 'Anything else?']


def say_address_name():
    return ['Great! Now I will ask you about your contact details. In the next steps you will need to specify your name, city, postal code and street & street number.', 'What\'s your name?']

def say_address_city():
    return ['What city do you live in?']

def say_address_code():
    return ['Postcode?']

def say_address_code_incorrect():
    return ['Please provide correct 5 digit postcode.']

def check_address_code(code):
    return len(str(code)) == 5
        
def say_address_street():
    return ['To finish, I need your street name and house number.']

def say_address_street_incorrect():
    return ['Please provide the street name and your house number.']

def say_confirm_address(address):
    return [address, 'Is this correct?']

def say_wrong():
    return ['What\'s wrong?']

def say_summary():
    return ['Here is the summary of your order:\n' + order.__str__() + '\n' + address.__str__(), 'Hold tight. We will be there in 20 minutes!']

def say_options():
    global state
    if state == State.GREETINGS or state == State.ORDER:
        return ['I\'m sorry, I don\'t understand - I\'m just a bot. You can ask me to show you the menu or go straight to ordering your pizza if you are familiar with the process.']
    elif state == State.ADDRESS:
        return ['I\'m sorry, I don\'t understand - I\'m just a bot. I need to know where to deliver your order.'] + say_address_name()
    elif state == State.ADDRESS_NAME:
        return ['I\'m sorry, I don\'t understand - I\'m just a bot. I need to know where to deliver your order.'] + say_address_city()
    elif state == State.ADDRESS_CITY:
        return ['I\'m sorry, I don\'t understand - I\'m just a bot. I need to know where to deliver your order.'] + say_address_code()
    elif state == State.ADDRESS_CODE:
        return ['I\'m sorry, I don\'t understand - I\'m just a bot. I need to know where to deliver your order.'] + say_address_street()





# Define a few command handlers. These usually take the two arguments bot and
# update. Error handlers also receive the raised TelegramError object in error.
def start(bot, update):
    """Send a message when the command /start is issued."""
    update.message.reply_text('Ready for action.')


def get_intent(bot, update):
    client = Wit(wit_access_token)
    response = client.message(update.message.text)
    replies = parse_response(response)
    for reply in replies:
        bot.send_chat_action(chat_id=update.message.chat_id, action=telegram.ChatAction.TYPING)
        sleep(0.7)
        update.message.reply_text(reply)


def error(bot, update, error):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, error)


def main():
    """Start the bot."""
    # Create the EventHandler and pass it your bot's token.
    updater = Updater(telegram_access_token)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help))

    dp.add_handler(MessageHandler(Filters.text, get_intent))

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
