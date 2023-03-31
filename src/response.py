import discord
import asyncio
from discord.ext import commands
from EdgeGPT import Chatbot, ConversationStyle
from src import log
from config import load_config
from functools import partial

logger = log.setup_logger(__name__)
USE_SUGGEST_RESPONSES = load_config.config["USE_SUGGEST_RESPONSES"]
sem = asyncio.Semaphore(1)

# to add suggest responses
class MyView(discord.ui.View):
    def __init__(self, chatbot: Chatbot, conversation_style:str, suggest_responses:list):
        super().__init__(timeout=120)
        # add buttons
        for label in suggest_responses:
            button = discord.ui.Button(label=label)
            # button event
            async def callback(interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.defer(ephemeral=False, thinking=True)
                # when click the button, all buttons will disable.
                for child in self.children:
                    child.disabled = True
                await interaction.followup.edit_message(message_id=interaction.message.id, view=self)
                self.clear_items()
                username = str(interaction.user)
                usermessage = button.label
                channel = str(interaction.channel)
                logger.info(f"\x1b[31m{username}\x1b[0m : '{usermessage}' ({channel}) [Style: {conversation_style}] [button]")
                task = asyncio.create_task(send_message(chatbot, interaction, usermessage, conversation_style))
                await asyncio.gather(task)
            self.add_item(button)
            self.children[-1].callback = partial(callback, button=button)

async def send_message(chatbot: Chatbot, message: discord.Interaction, user_message: str, conversation_style: str):
    async with sem:
        import re
        superscript_map = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'}
        reply = ''
        text = ''
        embed = ''
        all_url = []
        try:
            ask = f"> **{user_message}** - <@{str(message.user.id)}> (***style: {conversation_style}***)\n\n"
            # change conversation style
            if conversation_style == "creative":
                reply = await chatbot.ask(prompt=user_message, conversation_style=ConversationStyle.creative, wss_link="wss://sydney.bing.com/sydney/ChatHub")
            elif conversation_style == "precise":
                reply = await chatbot.ask(prompt=user_message, conversation_style=ConversationStyle.precise, wss_link="wss://sydney.bing.com/sydney/ChatHub")
            else:
                reply = await chatbot.ask(prompt=user_message, conversation_style=ConversationStyle.balanced, wss_link="wss://sydney.bing.com/sydney/ChatHub")
            # get reply text
            text = f"{reply['item']['messages'][1]['text']}"
            text = re.sub(r'\[\^(\d+)\^\]', lambda match: ''.join(superscript_map.get(digit, digit) for digit in match.group(1)), text)
            text = re.sub(r"(?<=^ {0,6})-", "⦁", text)
            # Get the URL, if available
            if len(reply['item']['messages'][1]['sourceAttributions']) != 0:
                for i, url in enumerate(reply['item']['messages'][1]['sourceAttributions'], start=1):
                    if len(url['providerDisplayName']) == 0:
                        all_url.append(f"{i}: [{url['seeMoreUrl']}]({url['seeMoreUrl']})")
                    else:
                        all_url.append(f"{i}: [{url['providerDisplayName']}]({url['seeMoreUrl']})")
                link_text = "\n".join(all_url)
                embed = discord.Embed(description=link_text)
            response = f"{ask}{text}"
            # discord limit about 2000 characters for a message
            while len(response) > 2000:
                temp = response[:2000]
                response = response[2000:]
                await message.followup.send(temp)
            # add all suggest responses in list
            if USE_SUGGEST_RESPONSES:
                suggest_responses = []
                for suggest in reply["item"]["messages"][1]["suggestedResponses"]:
                    suggest_responses.append(suggest["text"])
                if embed:
                    await message.followup.send(response, view=MyView(chatbot, conversation_style,  suggest_responses), embeds=[embed])
                else:
                    await message.followup.send(response, view=MyView(chatbot, conversation_style, suggest_responses))
            else:
                if embed:
                    await message.followup.send(response, embeds=[embed])
                else:
                    await message.followup.send(response)
        except Exception as e:
                print(reply)
                if reply["item"]["throttling"]["numUserMessagesInConversation"] and reply["item"]["throttling"]["numUserMessagesInConversation"] > reply["item"]["throttling"]["maxNumUserMessagesInConversation"]:
                    await message.followup.send("> **Oops, I think we've reached the end of this conversation. Please reset the bot!**")
                    logger.exception(f"Error while sending message: The maximum number of conversations in a round has been reached")
                elif reply["item"]["result"]["value"] and reply["item"]["result"]["value"] == "Throttled":
                    await message.followup.send("> **Error: We're sorry, but you've reached the maximum number of messages you can send to Bing in a 24-hour period. Check back later!**")
                    logger.exception("Error while sending message: The daily conversation limit has been reached")
                else:
                    await message.followup.send("> **Please try again later or reset bot**")
                    logger.exception(f"Error while sending message: {e}")
