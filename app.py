from flask import Flask, render_template, request
import openai
import os
import redis
import sys

app = Flask(__name__)
redis = redis.Redis(host='redis', port=6379, db=0)

# Inference parameters
TEMPERATURE=0.4
MAX_TOKENS=2000
TOP_P=1.0
FREQUENCY_PENALTY=0.6
PRESENCE_PENALTY=0.0
STOP="."

if not 'OPENAI_API_KEY' in os.environ:
  raise Exception('Environment variable OPENAI_API_KEY is required')
else:
  OPENAI_API_KEY = os.environ['OPENAI_API_KEY']

@app.route('/')
def index():
  return render_template('index.html')

@app.route('/prompt_tester', methods=['GET'])
def prompt_tester():
  return render_template('prompt_tester.html')
  if None not in (request.form['prompt'], request.form['test']):
    prompt = request.form['prompt']
    test = request.form['test']
    test_result = test_prompt(prompt, test)
    return render_template('prompt_tester.html', test_result=test_result)

@app.route('/prompt_test', methods=['POST'])
def prompt_test():
  prompt = request.form['prompt']
  test = request.form['test']
  test_result = test_prompt(prompt, test)
  return str(test_result)

@app.route('/prompt_compare', methods=['GET'])
def prompt_compare():
  print("Loaded prompt compare view", file=sys.stderr)
  return render_template('prompt_compare.html')

@app.route('/prompt_comparison', methods=['POST'])
def prompt_comparison():
  first_prompt = request.form['first_prompt']
  second_prompt = request.form['second_prompt']
  test = request.form['test']
  iterations = int(request.form['iterations'])
  print(f"Comparing prompts {iterations} time(s)", file=sys.stderr)
  better_results = {
    "first_prompt": 0,
    "second_prompt": 0
  }
  for i in range(0, iterations):
    comparison = compare_prompts(first_prompt, second_prompt, test)
    if comparison is True:
      better_results["first_prompt"] += 1
      reason = qualitative_comparison(first_prompt, second_prompt, test)
    elif comparison is False:
      better_results["second_prompt"] += 1
      reason = qualitative_comparison(second_prompt, first_prompt, test)


  if better_results['first_prompt'] > better_results['second_prompt']:
    return f"After {iterations}, first prompt is better ({better_results['first_prompt'] / iterations * 100}%) because {reason}. More suggestions: {recommend_more_prompts(first_prompt, test, reason)}"
  elif better_results['first_prompt'] < better_results['second_prompt']:
    return f"After {iterations}, second prompt is better ({better_results['second_prompt'] / iterations * 100}%) because {reason}. More suggestions: {recommend_more_prompts(second_prompt, test, reason)}"
  else:
    return f"After {iterations}, prompts are tied"

@app.route('/prompt', methods=['POST'])
def prompt():
  prompt = request.form['prompt']
  # if prompt.startswith('DEPLOY'):
  #   response = openAi.Completion
  # else:
  response = openai.Completion.create(
    model='text-davinci-003',
    prompt=prompt,
    temperature=TEMPERATURE,
    max_tokens=MAX_TOKENS,
    top_p=TOP_P,
    frequency_penalty=FREQUENCY_PENALTY,
    presence_penalty=PRESENCE_PENALTY,
    stop=STOP
  ).choices[0].text
  print(f"Got response: {response}", file=sys.stderr)
  put_context('chats', prompt + "\n" + response)
  return response + "\n" + get_context('chats')

def get_context_tag(message):
  context_tag = openai.Completion.create(
    model='text-davinci-003',
    prompt=message + "\n I want you to summarize the above in the single most identifiable word (a tag) from the following: people, places, events, conversations. Do not say more than one word, and only choose one of these options.",
    temperature=0.1,
    max_tokens=MAX_TOKENS,
    top_p=TOP_P,
    frequency_penalty=FREQUENCY_PENALTY,
    presence_penalty=PRESENCE_PENALTY,
    stop=STOP
  ).choices[0].text
  return context_tag

def get_context(context_tag):
  context = redis.get(context_tag)
  print(f"Redis got context: {context}", file=sys.stderr)
  return context

def put_context(context_tag, additional_context):
  print(f"Putting context: {additional_context}", file=sys.stderr)
  old_context = get_context(context_tag)
  if old_context is None:
    new_context = additional_context
    return new_context
  else:
  #   pre_prompt = "I am going to have you recontextualize some information. I will give you a context, and then a message. You will then recontextualize the response to fit the context. The context will begin with BEGIN CONTEXT and end with END CONTEXT. The message will begin with BEGIN MESSAGE and END MESSAGE.\n"
  #   mid_prompt = "BEGIN CONTEXT\n" + str(old_context) + "\nEND CONTEXT\nBEGIN MESSAGE\n" + additional_context + "\nEND MESSAGE\n"
  #   prompt = pre_prompt + mid_prompt + "Integrate the message into the context by recontextualizing the message into the context. You are free to expand the length of the context as much as necessary to contain all the important parts. If you are not sure how to summarize, keep the message verbatim.\n"

    prompt = str(old_context) + "\n" + additional_context + "\n" + "Resummarize, recontextualize, and de-duplicate everything:\n\n"

    new_context = openai.Completion.create(
      model="text-davinci-003",
      prompt=prompt,
      temperature=TEMPERATURE,
      max_tokens=MAX_TOKENS,
      top_p=TOP_P,
      frequency_penalty=FREQUENCY_PENALTY,
      presence_penalty=PRESENCE_PENALTY,
      stop="\n\n"
    ).choices[0].text
    redis.set(context_tag, new_context)
    print(f"Put context: {new_context}", file=sys.stderr)
    return new_context

def test_prompt(prompt, test):
  """ Given a prompt, and a test, check whether the test is true of the results generated by the prompt. """
  print(f"Testing prompt: {prompt}", file=sys.stderr)
  response = openai.Completion.create(
    model='text-davinci-003',
    prompt=prompt,
    temperature=TEMPERATURE,
    max_tokens=MAX_TOKENS,
    top_p=TOP_P,
    frequency_penalty=FREQUENCY_PENALTY,
    presence_penalty=PRESENCE_PENALTY
  ).choices[0].text
  print(f"Got response: {response}", file=sys.stderr)
  test_result = openai.Completion.create(
    model='text-davinci-003',
    prompt=f"{response}\n{test}\n",
    temperature=TEMPERATURE,
    max_tokens=MAX_TOKENS,
    top_p=TOP_P,
    frequency_penalty=FREQUENCY_PENALTY,
    presence_penalty=PRESENCE_PENALTY
  ).choices[0].text.lower()

  print(f"Got test result: {test_result}", file=sys.stderr)
  
  if "true" in test_result and "false" in test_result:
    raise Exception(f'Test result {test_result} was ambiguous')
  elif "yes" in test_result and "no" in test_result:
    raise Exception(f'Test result {test_result} was ambiguous')
  elif "true" in test_result and "no" in test_result:
    raise Exception(f'Test result {test_result} was ambiguous')
  elif "false" in test_result and "yes" in test_result:
    raise Exception(f'Test result {test_result} was ambiguous')
  elif "true" in test_result:
    return True
  elif "yes" in test_result:
    return True
  elif "false" in test_result:
    return False
  elif "no" in test_result:
    return False
  else:
    raise Exception(f'Test result {test_result} was unexpected format')

def compare_prompts(first_prompt, second_prompt, test, iterations = 1):
  """ Given two prompts, and a test, check whether the test is true of the results generated by the first prompt more often than the second prompt. """
  first_prompt_results = []
  second_prompt_results = []
  for i in range(iterations):
    first_prompt_results.append(test_prompt(first_prompt, test))
    second_prompt_results.append(test_prompt(second_prompt, test))
  first_prompt_successes = sum(first_prompt_results)
  second_prompt_successes = sum(second_prompt_results)
  if first_prompt_successes > second_prompt_successes:
    return True
  elif first_prompt_successes < second_prompt_successes:
    return False
  else:
    return None

def qualitative_comparison(better_prompt, worse_prompt, test):
  """ Given a better prompt and a worse prompt, return a qualitative comparison of why the better prompt is better"""
  print("Qualitative comparison", file=sys.stderr)
  prompt = "We want to write a prompt that generates results that consistently satisfy a test. Given a better prompt, a worse prompt, and a test, explain what differentiates the better prompt from the worse prompt. (Phrase like this: 'A better prompt should...')"
  prompt += "\nBetter prompt:\n" + better_prompt
  prompt += "\nWorse prompt:\n" + worse_prompt
  prompt += "\nTest:\n" + test
  response = openai.Completion.create(
    model='text-davinci-003',
    prompt=prompt,
    temperature=TEMPERATURE,
    max_tokens=MAX_TOKENS,
    top_p=TOP_P,
    frequency_penalty=FREQUENCY_PENALTY,
    presence_penalty=PRESENCE_PENALTY,
    stop=STOP
  ).choices[0].text
  return response

def recommend_more_prompts(prompt, test, guidelines = "", n = 1):
  """ Given a prompt, a test, and optionally some guidelines, return a prompt that is similar to the given prompt, but that is different in some way. """
  print("Recommend more comparisons", file=sys.stderr)
  prompt += "Prompt:\n" + prompt
  prompt += "Test:\n" + test
  prompt += "Guidelines:\n" + guidelines
  prompt += "Return a prompt that is similar to the given prompt, but that is different in some way:\n"
  response = openai.Completion.create(
    model='text-davinci-003',
    prompt=prompt,
    temperature=0.6,
    max_tokens=MAX_TOKENS,
    top_p=TOP_P,
    frequency_penalty=FREQUENCY_PENALTY,
    presence_penalty=PRESENCE_PENALTY,
    stop=':'
  ).choices[0].text
  return response

def deploy_code(current_code, change_request):
    # Use the OpenAI API to request a code update
    response = openai.Code.create(
        model='code-davinci-002',
        prompt=f"{current_code}\n{change_request}",
        temperature=0.5,
        max_tokens=1024
    ).choices[0].code

    # Extract the updated code from the response
    updated_code = response['choices'][0]['text']

    # Replace the current code with the updated code in memory
    exec(updated_code, globals())

    # Write the updated code to a file in the current directory
    with open('updated_code.py', 'w') as f:
        f.write(updated_code)


    # Return a message to confirm that the code has been updated
    return "Code updated successfully"


if __name__ == '__main__':
  app.run(host='0.0.0.0', port=8080, debug=True)
