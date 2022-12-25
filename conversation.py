#!/usr/bin/env python
import json
import openai
import os

if not 'OPENAI_API_KEY' in os.environ:
  raise Exception('Environment variable OPENAI_API_KEY is required')

DATA = json.load(open('./data.json'))
bot_name = os.environ.get('BOT_NAME')
data = data['items']
context = data['context'][bot_name]
last_item = data[-1]
last_speaker = last_conversation_item['speaker']

if last_speaker == bot_name:
  print('Bot was last to speak, exiting.')
  exit()

# Build the prompt with the previous 10 conversation items and the context
prompt = ""
for i in range(max(0, len(conversation) - 10), len(conversation)):
  conversation_item = conversation[i]
  prompt += conversation_item['speaker'] + ": " + conversation_item['text'] + "\n"
prompt += get_context() + "\n" + last_conversation_item['speaker'] + ":" + last_conversation_item['text']

response = openai.Completion.create(
  model="text-davinci-003",
  prompt=prompt + "I want you to respond only as " + bot_name + ":",
  temperature=0.9,
  max_tokens=2000,
  top_p=1.0,
  frequency_penalty=0.6,
  presence_penalty=0.0,
).choices[0].text

conversation.append({"speaker": bot_name, "text": response})
# write them back to file
data['conversation'] = conversation
data['context'][bot_name]['conversation'] = put_context(DATA['context']['context_tag'], 
)
with open('./conversations/data.json', 'w') as outfile:
  json.dump(data, outfile)

  DATA['context']['context_tag'] =   DATA['context']['context_tag'] = new_context



def get_context(context_tag):
  DATA['context']['context_tag'] = new_context

def put_context(old_context message_text, context_tag, model="text-davinci-003", temperature=0.4, max_tokens=2000, top_p=1.0, frequency_penalty=0.6, presence_penalty=0.0):
  pre_prompt = "I am going to have you recontextualize some information. I will give you a context, and then a message. You will then recontextualize the response to fit the context. The context will begin with BEGIN CONTEXT and end with END CONTEXT. The message will begin with BEGIN MESSAGE and END MESSAGE.\n"
  mid_prompt = "BEGIN CONTEXT\n" + old_context + "\nEND CONTEXT\nBEGIN MESSAGE\n" + message_text + "\nEND MESSAGE\n"
  prompt = pre_prompt + mid_prompt + "Integrate the message into the context by recontextualizing the message into the context. You are free to expand the length of the context as much as necessary to contain all the important parts.\n"
  new_context = openai.Completion.create(
    model="text-davinci-003",
    prompt=prompt,
    temperature=temperature,
    max_tokens=max_tokens,
    top_p=top_p,
    frequency_penalty=frequency_penalty,
    presence_penalty=presence_penalty,
  ).choices[0].text
  return new_context