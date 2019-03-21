# navtex_bot
This python program is a Telegram bot that broadcasts Navtex messages.

If you only want to use it look for @Navtexbot in Telegram. I have only added the Navtex areas that I use so if you need more, you can fill the xml and send it to me or run your own instance of the bot.

In order to install:
1. Clone this repository to your machine
2. Install virtualenv `pip install virtualenv --user`
3. Create a virtualenv `virtualenv -p python3 navtex_bot`
4. Activate the virtualenv `cd navtex_bot && source bin/activate`
5. Install python requirements `pip install -r requirements.txt`
6. Run the program `python navtexbot.py apikey`. You can always use nohup or any other tool to leave the process running after closing the terminal: `nohup python navtexbot.py apikey &> salida.out&`
