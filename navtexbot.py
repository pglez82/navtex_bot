import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, PicklePersistence
import logging
import navtex
import sys


class NavtexBot:

    # Define a few command handlers. These usually take the two arguments bot and
    # update. Error handlers also receive the raised TelegramError object in error.
    def help(self,bot, update):
        """Send a message when the command /help is issued."""
        update.message.reply_text('This is the list of commands that you can use:\n'+
                                  '/listmetareas - lists all the Navtex METAREAS supported by the bot\n'+
                                  '/subscribe2messages - Subscribe to Navtex messages. You will chose an area and you will receive messages from this area\n'+
                                  '/unsubscribe2messages - Stop receiving messages from an area\n'+
                                  '/listsubscriptions - Check the messages you are subscribed to\n'+
                                  '/getmessages - Get messages from your subscriptions. Do not wait until messages are automatically sent to you. You will get the last message available.')

    def start(self,bot,update):
        update.message.reply_text('Welcome! You can check the commands available with the command /help.')

    def listmetareas(self, bot, update):
        reply = ""
        for metarea in self.metareas:
            reply = reply + 'METAREA ' + metarea['id'] + ' - ' + metarea['description']+'\n'
        update.message.reply_text(reply)


    def subscribe2messages(self,bot, update, user_data):
        buttons = []
        buttons.append([])
        for metarea in self.metareas:
            buttons[0].append(InlineKeyboardButton("METAREA "+metarea['id'], callback_data='MA'+metarea['id']))

        reply_markup = InlineKeyboardMarkup(buttons)

        update.message.reply_text('Please choose a METAREA:', reply_markup=reply_markup)


    def unsubscribe2messages(self,bot, update, user_data):
        if "subscriptions" not in user_data or not user_data["subscriptions"]:
            reply="You are not subscribed to any Navtex message. Nothing to unsubscribe!"
            update.message.reply_text(reply)
        else:
            reply="Choose the message to unsubscribe to: "
            buttons = []
            for message in user_data['subscriptions']:
                buttons.append([InlineKeyboardButton('X ' + message, callback_data='UMSG'+message)])
            reply_markup = InlineKeyboardMarkup(buttons)
            update.message.reply_text(reply, reply_markup=reply_markup)

    def listsubscriptions(self,bot, update, user_data):
        if "subscriptions" not in user_data or not user_data['subscriptions']:
            reply="You are not subscribed to any Navtex message. Use the command /subscribe2messages in order to subscribe."
        else:
            reply="You are subscribed to:\n"
            for message in user_data['subscriptions']:
                times = self.s.get_message_times(message)
                reply=reply + message
                for time in times:
                    reply = reply + ' ' + time.strftime('%H:%M')
                reply = reply + ' (UTC)\n'

        update.message.reply_text(reply)


    def buttonhandler_metareas(self,bot, update, user_data):
        query = update.callback_query
        metarea = query.data[2:]
        messages = self.s.get_area_messages(metarea)
        buttons = []
        for message in messages:
            buttons.append([InlineKeyboardButton(message['id'],callback_data='MSG'+message['id'])])

        reply_markup = InlineKeyboardMarkup(buttons)
        bot.edit_message_text(text="Selected METAREA {}. Choose the message you want to subscribe:".format(metarea),
                          chat_id=query.message.chat_id,
                          message_id=query.message.message_id,
                          reply_markup=reply_markup)


    def buttonhandler_subscribe(self,bot, update, user_data):
        query = update.callback_query
        message = query.data[3:]
        times = self.s.get_message_times(message)
        if self.add_user_subscription(message,user_data,query.message.chat_id):
            reply = "You are now subscribed to messages in "+message+". These messages will arrive at"
            for time in times:
                reply = reply + ' ' + time.strftime('%H:%M')
            reply = reply + ' (UTC)'
            bot.edit_message_text(text=reply,
                              chat_id=query.message.chat_id,
                              message_id=query.message.message_id)
        else:
            bot.edit_message_text(text="You were already subscribed to this message",
                              chat_id=query.message.chat_id,
                              message_id=query.message.message_id)

    def buttonhandler_unsubscribe(self,bot, update, user_data):
        query = update.callback_query
        message = query.data[4:]

        self.remove_user_subscription(message, user_data)
        reply = "Succesfully unsubscribed from  "+message
        bot.edit_message_text(text=reply,
                          chat_id=query.message.chat_id,
                          message_id=query.message.message_id)

    def getmessages(self,bot, update, user_data):
        for message in user_data['subscriptions']:
            msg = self.downloader.get_stored_message(message)
            self.send_message(bot,update.message.chat_id,msg)

    def add_user_subscription(self, message, user_data, chat_id):
        if "subscriptions" not in user_data:
            user_data['subscriptions'] = []
        if message in user_data['subscriptions']:
            return False
        else:
            user_data['subscriptions'].append(message)
            user_data['chat_id']=chat_id
            self.logger.info("User with chat_id="+str(user_data['chat_id'])+" has subscribed to "+message)
            self.my_persistence.flush()
            return True

    def remove_user_subscription(self, message, user_data):
        user_data['subscriptions'].remove(message)
        self.logger.info("User with chat_id="+str(user_data['chat_id'])+" has removed the subscription to message "+message)
        self.my_persistence.flush()

    def new_message_received(self,messageid,messagecontent):
        self.logger.info("New message received: "+messageid+". Computing users to send it to.")
        #Compute to which users we need to send the messages
        user_data=self.my_persistence.get_user_data()
        chat_ids = []
        for key, value in user_data.items():
            if messageid in value['subscriptions']:
                chat_ids.append(value['chat_id'])
        self.logger.info("Sending message to these users: "+str(chat_ids))

        message_number = 0
        for chat_id in chat_ids:
            self.logger.info("Sending message "+messageid+" to "+str(chat_id))
            #We cant send more than 30 messages per second, so we should count how many we are sending. We are going to be conservative. only 20 messages per second
            job_queue = self.updater.job_queue
            job_queue.run_once(lambda bot, job, chat_id=chat_id: (self.send_message(bot,chat_id,messagecontent)), message_number//20)
            message_number = message_number + len(messagecontent)//telegram.constants.MAX_MESSAGE_LENGTH+1

    def send_message(self, bot, chat_id, text: str, **kwargs):
        try:
            if len(text) <= telegram.constants.MAX_MESSAGE_LENGTH:
                return bot.send_message(chat_id, text, **kwargs)

            parts = []
            while len(text) > 0:
                if len(text) > telegram.constants.MAX_MESSAGE_LENGTH:
                    part = text[:telegram.constants.MAX_MESSAGE_LENGTH]
                    first_lnbr = part.rfind('\n')
                    if first_lnbr != -1:
                        parts.append(part[:first_lnbr])
                        text = text[first_lnbr:]
                    else:
                        parts.append(part)
                        text = text[telegram.constants.MAX_MESSAGE_LENGTH:]
                else:
                    parts.append(text)
                    break

            msg = None
            part_count = 0
            for part in parts:
                part_count = part_count + 1
                self.logger.info("Sending part "+str(part_count)+"to user "+str(chat_id))
                msg = bot.send_message(chat_id, part, **kwargs)
            return msg
        except telegram.error.Unauthorized: #The user might have blocked us
            self.logger.info("User might have blocked the bot: "+str(chat_id))


    def error(self,bot, update, error):
        """Log Errors caused by Updates."""
        self.logger.warning('Update "%s" caused error "%s"', update, error)

    def __init__(self):
        #Configure logging
        # Enable logging
        if len(sys.argv)<2:
            print("You need to pass a telegram api key as an argument...")
            exit(-1)

        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        self.logger.info("Arrancando el bot")

        self.s = navtex.NavtexSchedule(self.logger)
        self.metareas = self.s.get_metareas()
        self.my_persistence = PicklePersistence(filename='user_data',store_chat_data=False,on_flush=True)
        self.updater = Updater(sys.argv[1],persistence=self.my_persistence)
        self.downloader = navtex.NavtexDowloader(self.new_message_received,self.logger)

        # Get the dispatcher to register handlers
        dp = self.updater.dispatcher

        # on different commands - answer in Telegram
        dp.add_handler(CommandHandler("help", self.help))
        dp.add_handler(CommandHandler("start", self.start))
        dp.add_handler(CommandHandler("listmetareas", self.listmetareas))
        dp.add_handler(CommandHandler("subscribe2messages", self.subscribe2messages,pass_user_data=True))
        dp.add_handler(CommandHandler("unsubscribe2messages", self.unsubscribe2messages,pass_user_data=True))
        dp.add_handler(CommandHandler("getmessages", self.getmessages,pass_user_data=True))
        dp.add_handler(CommandHandler("listsubscriptions", self.listsubscriptions,pass_user_data=True))
        dp.add_handler(CallbackQueryHandler(self.buttonhandler_metareas,pattern='MA',pass_user_data=True))
        dp.add_handler(CallbackQueryHandler(self.buttonhandler_subscribe,pattern='MSG',pass_user_data=True))
        dp.add_handler(CallbackQueryHandler(self.buttonhandler_unsubscribe,pattern='UMSG',pass_user_data=True))



        # log all errors
        dp.add_error_handler(self.error)

        # Start the Bot
        self.updater.start_polling()

        #Start the scrapper
        self.downloader.start()

        # Run the bot until you press Ctrl-C or the process receives SIGINT,
        # SIGTERM or SIGABRT. This should be used most of the time, since
        # start_polling() is non-blocking and will stop the bot gracefully.
        self.updater.idle()


NavtexBot()
