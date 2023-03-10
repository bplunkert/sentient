import concurrent.futures
from flask import Flask, render_template, request
import json
import openai
import os
import redis
import sys

app = Flask(__name__)
redis = redis.Redis(host='redis', port=6379, db=0)

# Inference parameters
TEMPERATURE=0.4
MAX_TOKENS=2000
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

@app.route('/conversation', methods=['GET', 'POST'])
def conversation():
  context_tag = request.args.get('context_tag')
  if context_tag is None:
    context_tag = 'conversation'
  conversation_history = redis.get(f"conversation.{context_tag}")

  if request.method == 'GET':
    return render_template('conversation.html', conversation_history=conversation_history)
  elif request.method == 'POST':
    context_tag = request.form['context_tag']
    context = get_context('context_tag')
    prompt = context + "\n" + conversation_history + "\n"  + request.form['prompt']

    response = openai.Completion.create(
      model='text-davinci-003',
      prompt=prompt,
      temperature=0.8,
      max_tokens=MAX_TOKENS,
      frequency_penalty=0.7,
      presence_penalty=0.1,
      stop=STOP
    ).choices[0].text

    put_context(context_tag, request.form['prompt'] + "\n" + response)
    return conversation_history

@app.route('/prompt', methods=['GET', 'POST'])
def prompt():
  if request.method == 'GET':
    return render_template('prompt.html')
  elif request.method == 'POST':
    prompt = request.form['prompt']
    response = openai.Completion.create(
      model='text-davinci-003',
      prompt=prompt,
      temperature=TEMPERATURE,
      max_tokens=MAX_TOKENS,
      frequency_penalty=FREQUENCY_PENALTY,
      presence_penalty=PRESENCE_PENALTY,
      stop=STOP
    ).choices[0].text
    print(f"Got response: {response}", file=sys.stderr)
    return response

@app.route('/prompt_compare', methods=['GET', 'POST'])
def prompt_compare():
  if request.method == 'GET':
    return render_template('prompt_compare.html')
  elif request.method == 'POST':
    first_prompt = request.form['first_prompt']
    second_prompt = request.form['second_prompt']
    test = request.form['test']
    iterations = int(request.form['iterations'])
    print(f"Comparing prompts {iterations} time(s)", file=sys.stderr)
    better_results = {
      "first_prompt": 0,
      "second_prompt": 0
    }

    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Create a list of tasks to run concurrently
        tasks = [executor.submit(compare_prompts, first_prompt, second_prompt, test) for i in range(iterations)]

        # Iterate over the completed tasks to count the results
        for task in concurrent.futures.as_completed(tasks):
            comparison = task.result()
            if comparison is True:
              better_results["first_prompt"] += 1
            elif comparison is False:
              better_results["second_prompt"] += 1

    # Determine the reason for the comparison result and assign it to the `reason` variable
    if better_results['first_prompt'] > better_results['second_prompt']:
      reason = qualitative_comparison(first_prompt, second_prompt, test)
      return f"After {iterations} iterations, first prompt is better ({better_results['first_prompt'] / iterations * 100}%) because {reason}. Recommend prompt(s): {json.dumps(recommend_prompts(test, first_prompt, reason, 3))}"
    elif better_results['first_prompt'] < better_results['second_prompt']:
      reason = qualitative_comparison(second_prompt, first_prompt, test)
      return f"After {iterations} iterations, second prompt is better ({better_results['second_prompt'] / iterations * 100}%) because {reason}. Recommend prompt(s):  {json.dumps(recommend_prompts(test, second_prompt, reason, 3))}"
    else:
      return f"After {iterations} iterations, both prompts are equally good.  Recommend prompt(s): {json.dumps(recommend_prompts(test, first_prompt, '', 3))},  {json.dumps(recommend_prompts(test, second_prompt, '', 3))}"

@app.route('/prompt_context', methods=['GET', 'POST'])
def prompt_context():
  if request.method == 'GET':
    return render_template('prompt_context.html')
  elif request.method == 'POST':
    prompt = request.form['prompt']
    context_tag = request.form['context_tag']
    response = openai.Completion.create(
      model='text-davinci-003',
      prompt=prompt,
      temperature=TEMPERATURE,
      max_tokens=MAX_TOKENS,
      frequency_penalty=FREQUENCY_PENALTY,
      presence_penalty=PRESENCE_PENALTY,
      stop=STOP
    ).choices[0].text
    print(f"Got response: {response}", file=sys.stderr)
    put_context(context_tag, prompt + "\n" + response)
    context = get_context(context_tag)

    output_response = "<br><strong>Response:</strong> " + response
    if context is not None:
      output_response += "<br><strong>Context:</strong> " + context

    return output_response

@app.route('/prompt_recommend', methods=['GET', 'POST'])
def prompt_recommend():
  if request.method == 'GET':
    return render_template('prompt_recommend.html')
  elif request.method == 'POST':
    return recommend_prompts(request.form['test'], request.form['prompt'], request.form['guidelines'], request.form['count'])

@app.route('/prompt_test', methods=['GET', 'POST'])
def prompt_test():
  if request.method == 'GET':
    return render_template('prompt_test.html')
  elif request.method == 'POST':
    prompt = request.form['prompt']
    test = request.form['test']
    test_result = test_prompt(prompt, test)
    return str(test_result)

#
# Non-route functions below:
#

def get_context_tag(message):
  context_tag = openai.Completion.create(
    model='text-davinci-003',
    prompt=message + "\n I want you to summarize the above in the single most identifiable word (a tag) from the following: people, places, events, conversations. Do not say more than one word, and only choose one of these options.",
    temperature=0.1,
    max_tokens=MAX_TOKENS,
    frequency_penalty=FREQUENCY_PENALTY,
    presence_penalty=PRESENCE_PENALTY,
    stop=STOP
  ).choices[0].text
  return context_tag

def get_context(context_tag):
  context = str(redis.get(context_tag))
  print(f"Redis got context: {context}", file=sys.stderr)
  return context

def put_context(context_tag, additional_context):
  print(f"Putting context: {additional_context}", file=sys.stderr)
  old_context = get_context(context_tag)
  if old_context is None:
    new_context = additional_context
  else:
    #pre_prompt = "I am going to have you recontextualize some information. I will give you a context, and then a message. You will then recontextualize the response to fit the context. The context will begin with BEGIN CONTEXT and end with END CONTEXT. The message will begin with BEGIN MESSAGE and END MESSAGE.\n"
    #mid_prompt = "BEGIN CONTEXT\n" + str(old_context) + "\nEND CONTEXT\nBEGIN MESSAGE\n" + additional_context + "\nEND MESSAGE\n"
    #prompt = pre_prompt + mid_prompt + "Integrate the message into the context by recontextualizing the message into the context. You are free to expand the length of the context as much as necessary to contain all the important parts. If you are not sure how to summarize, keep the message verbatim.\n"

    prompt = "Summary: \n" + str(old_context) + "\nNew material:\n" + additional_context + "\n" + "The summary should be in the form of a summary of a conversation, so that details can be recalled as needed. Resummarize, recontextualize the new material above into the summary above it:\n\n"

    new_context = openai.Completion.create(
      model="text-davinci-003",
      prompt=prompt,
      temperature=TEMPERATURE,
      max_tokens=MAX_TOKENS,
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
    frequency_penalty=FREQUENCY_PENALTY,
    presence_penalty=PRESENCE_PENALTY
  ).choices[0].text
  print(f"Got response: {response}", file=sys.stderr)
  test_result = openai.Completion.create(
    model='text-davinci-003',
    prompt=f"{response}\n{test}\n",
    temperature=TEMPERATURE,
    max_tokens=MAX_TOKENS,
    frequency_penalty=FREQUENCY_PENALTY,
    presence_penalty=PRESENCE_PENALTY
  ).choices[0].text.lower().strip()
  test_result_words = test_result
  print(f"Got test result: {test_result_words}", file=sys.stderr)
  
  if "true" in test_result_words and "false" in test_result_words:
    raise Exception(f'Test result {test_result} was ambiguous')
  elif "yes" in test_result_words and "no" in test_result_words:
    raise Exception(f'Test result {test_result} was ambiguous')
  elif "true" in test_result_words and "no" in test_result_words:
    raise Exception(f'Test result {test_result} was ambiguous')
  elif "false" in test_result_words and "yes" in test_result_words:
    raise Exception(f'Test result {test_result} was ambiguous')
  elif "true" in test_result_words:
    return True
  elif "yes" in test_result_words:
    return True
  elif "false" in test_result_words:
    return False
  elif "no" in test_result_words:
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
  prompt = "We want to write a prompt that generates results that consistently satisfy a test. Given a better prompt, a worse prompt, and a test, explain what differentiates the better prompt from the worse prompt. (Phrase like this: 'A better prompt should...'). Recommend changes to further refine the prompt and increase the test pass rate."
  prompt += "\nBetter prompt:\n" + better_prompt
  prompt += "\nWorse prompt:\n" + worse_prompt
  prompt += "\nTest:\n" + test
  response = openai.Completion.create(
    model='text-davinci-003',
    prompt=prompt,
    temperature=TEMPERATURE,
    max_tokens=MAX_TOKENS,
    frequency_penalty=FREQUENCY_PENALTY,
    presence_penalty=PRESENCE_PENALTY,
    stop=STOP
  ).choices[0].text
  return response


import concurrent.futures

def recommend_prompts(test, prompt = "", guidelines = "", n = 1):
    """ Given a test, and optionally a prompt and/or some guidelines, return a prompt that is similar to the given prompt, but that is different in some way. """
    print("Recommend more comparisons", file=sys.stderr)

    prompt_pre_tuning = ''
    prompt_pre_tuning += 'The test we want our prompt to return "yes" or "true" for. Test: "True or false, the above list includes a shark but does not include an elephant."'
    prompt_pre_tuning += '\nAn example prompt that might be used to attempt to pass our test. The recommendation made must be different from this prompt, in a way adhering to guidelines. Prompt: List four types of animals.'
    prompt_pre_tuning += '\nGuidelines that any recommended prompts should adhere to. Guidelines: Any prompt recommended should list four objects.'
    prompt_pre_tuning += '\nRecommend a prompt that is likely to return a "yes" or "true" answer for the test above, without making any reference to it. For example, if the test is checking a list, the prompt recommended should return a list. Recommendation:'

    prompt_string = prompt_pre_tuning + '\nThe test we want our prompt to return "yes" or "true" for: ' + test

    if prompt != '':
        prompt_string += "\nPrompt: " + prompt
    if guidelines != '':
        prompt_string += "\nGuidelines: " + guidelines
    prompt_string += "\nRecommendation: " 

    recommended_prompts = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Create a list of tasks to run concurrently
        tasks = [executor.submit(get_recommended_prompt, prompt_string) for i in range(int(n))]

        # Iterate over the completed tasks to get the recommended prompts
        for task in concurrent.futures.as_completed(tasks):
            recommended_prompt = task.result()
            recommended_prompts.append(recommended_prompt)

    return recommended_prompts

def get_recommended_prompt(prompt_string):
    """ Returns a recommended prompt by calling the OpenAI API with the given prompt string. """
    return openai.Completion.create(
        model='text-davinci-003',
        prompt=prompt_string,
        temperature=0.6,
        max_tokens=MAX_TOKENS,
        frequency_penalty=0.9,
        presence_penalty=0.9,
        stop=':'
    ).choices[0].text.strip()


# def deploy_code(current_code, change_request):
#     # Use the OpenAI API to request a code update
#     response = openai.Code.create(
#         model='code-davinci-002',
#         prompt=f"{current_code}\n{change_request}",
#         temperature=0.5,
#         max_tokens=1024
#     ).choices[0].code

#     # Extract the updated code from the response
#     updated_code = response['choices'][0]['text']

#     # Replace the current code with the updated code in memory
#     exec(updated_code, globals())

#     # Write the updated code to a file in the current directory
#     with open('updated_code.py', 'w') as f:
#         f.write(updated_code)


#     # Return a message to confirm that the code has been updated
#     return "Code updated successfully"


# def qualitative_estimation(first_prompt, second_prompt, test):
#   """ Given two prompts and a test, ask the inference engine to estimate which prompt is more likely to pass the chosen test """


if __name__ == '__main__':
  app.run(host='0.0.0.0', port=8080, debug=True)
