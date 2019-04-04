from requests import get
from requests.exceptions import RequestException
from contextlib import closing
from bs4 import BeautifulSoup
import re
import xml.etree.ElementTree
from datetime import datetime
import pytz
import schedule
import time
from dateutil import tz
from threading import Thread



class NavtexSchedule:
    def __init__(self, logger):
        self.metareas = xml.etree.ElementTree.parse('navtex.xml').getroot()
        self.logger = logger

    def get_metareas(self):
        ids = []
        for metarea in self.metareas.findall('metarea'):
            ids.append({'id':metarea.get('id'),'url':metarea.get('url'),'description':metarea.get('description')})
        return ids

    def get_area_messages(self,metarea):
        metareaxml=self.metareas.find("metarea[@id='"+metarea+"']")
        messagesxml = metareaxml.getchildren()[0]
        messages = []
        for messagexml in messagesxml:
            times = []
            for time in messagexml.getchildren()[0]:
                times.append(datetime.strptime(time.text,"%H:%M:%S").replace(tzinfo=pytz.UTC))
            messages.append({'id':messagexml.get('id'),'times':times})

        return messages

    def get_message_times(self,message):
        messagexml=self.metareas.find(".//message[@id='"+message+"']")
        times = []
        for time in messagexml.getchildren()[0]:
            times.append(datetime.strptime(time.text,"%H:%M:%S").replace(tzinfo=pytz.UTC))
        return times


class NavtexScrapper:
    def __init__(self,logger):
        self.logger = logger

    def simple_get(self,url):
        """
        Attempts to get the content at `url` by making an HTTP GET request.
        If the content-type of response is some kind of HTML/XML, return the
        text content, otherwise return None.
        """
        try:
            with closing(get(url, stream=True)) as resp:
                if self.is_good_response(resp):
                    return resp.content
                else:
                    return None

        except RequestException as e:
            self.log_error('Error during requests to {0} : {1}'.format(url, str(e)))
            return None

    def is_good_response(self,resp):
        """
        Returns True if the response seems to be HTML, False otherwise.
        """
        content_type = resp.headers['Content-Type'].lower()
        return (resp.status_code == 200
                and content_type is not None
                and content_type.find('html') > -1)

    def log_error(self,e):
        """
        It is always a good idea to log errors.
        This function just prints them, but you can
        make it do anything.
        """
        self.logger.error(e)

    #Example 'http://weather.gmdss.org/III.html'
    def get_bulletin(self,url,message):
        """
        Gets a bulletin and returns it as text
        :param url: the url of the area
        :param message: the id of the message
        :return: the text of the bulletin
        """
        raw_html = self.simple_get(url)
        if raw_html != None:
            self.logger.info("Getting url for message "+message)
            html = BeautifulSoup(raw_html, 'html.parser')
            link = html.find('a', attrs={'href': re.compile("^bulletins/"+message)})
            linkp=link.get('href')
            bulletinurl = "http://weather.gmdss.org/"+linkp.replace(".html",".txt")
            self.logger.info("The url has been obtained for the message: "+bulletinurl+".Downloading...")
            return get(bulletinurl).content.decode('latin1')
        else:
            return None


class NavtexDowloader(Thread):
    """
    This object schedules the download of all the bulletins at the corresponding time using a new thread for each
    """
    def download(self, url, message, retry=False):
        self.logger.info("Downloading message "+message)
        messagecontent = self.scrapper.get_bulletin(url,message)
        if messagecontent != None:
            self.logger.info("Message ["+message+"] downloaded properly.")

            #Remove annoying breaklines
            messagecontent = re.sub(r'(\w)\n(\w)', r'\1 \2', messagecontent) #being in brackets we form a group. We can make a reference to that group using \1
            #We store the message
            self.messages[message] = messagecontent

            #We call the callback in order to send the message by telegram
            if self.send_messages:
                self.function_callback(message,messagecontent)
            #This job was just lanched after a network fail so we cancel it after finnishing it
            if retry:
                self.logger.info("This job has been just lanched to redownload a message ["+message+"] that failed. We got the message so we cancel it")
                return schedule.CancelJob
        else:
            if retry:
                self.logger.error("We are retrying but we still where not able to download the message ["+message+"]. Thread should retry again in one minute.")
            else:
                self.logger.error("Message ["+message+"] could not be downloaded. Reescheduling the job every 1 minute to try to download the message")
                schedule.every(1).minutes.do(self.download, url, message, True)



    def get_stored_message(self,message):
        if message not in self.messages:
            return "The message do not exist in the server. Please wait until the message is downloaded again."
        else:
            return self.messages[message]

    def time_to_localtime(self,t):
        return t.astimezone(tz.tzlocal()).strftime('%H:%M')

    def __init__(self,function_callback, logger):
        """
        Checks the schedule (from the xml) and schedules all the downloads in order to be executed. The threads gets then blocked
        """
        super().__init__()
        self.logger = logger

        self.send_messages = False

        self.function_callback = function_callback
        self.messages = {}

        s = NavtexSchedule(logger)
        self.scrapper = NavtexScrapper(logger)
        for metarea in s.get_metareas():
            for message in s.get_area_messages(metarea['id']):
                for t in message['times']:
                    schedule.every().day.at(self.time_to_localtime(t)).do(self.download,metarea['url'],message['id'])


    def run(self):
        #schedule.run_all(5)
        self.send_messages = True
        while 1:
            schedule.run_pending()
            time.sleep(5)


