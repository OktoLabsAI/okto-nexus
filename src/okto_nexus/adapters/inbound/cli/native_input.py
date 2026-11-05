"""Render the existing native question forms in a terminal, without defaults."""
import json
import math

from ....application.terminal_connection import ConnectionError


def display_text(value):
    return ''.join(char if char in '\n\t' or ord(char) >= 32 and not 127 <= ord(char) <= 159
                   else f'\\u{ord(char):04x}' for char in str(value))


def _select(options, *, multiple=False, other=False):
    for index, option in enumerate(options, 1):
        print(f'{index}. {display_text(option)}')
    if other:
        print('0. Write another answer')
    raw = input('Choose numbers separated by commas: ' if multiple else 'Choose a number: ').strip()
    try:
        indices = [int(item.strip()) for item in raw.split(',')]
        if not indices or len(set(indices)) != len(indices) or not multiple and len(indices) != 1:
            raise ValueError
        if any(index < (0 if other else 1) or index > len(options) for index in indices):
            raise ValueError
    except ValueError:
        raise ConnectionError('ANSWER_REQUIRED', 'Select an explicit listed answer.') from None
    answers = [input('Your answer: ') if index == 0 else options[index - 1] for index in indices]
    if any(not answer for answer in answers):
        raise ConnectionError('ANSWER_REQUIRED', 'Enter a nonempty answer.')
    return answers


def answer(proposal):
    """Return an explicit decision/answer; the Server validates the real schema."""
    key = proposal['approval_key']
    print(f"Request {display_text(key['canonical_request_id'])} · agent {display_text(key['agent_id'])} · session {display_text(key['session_id'])}")
    print('Expires: ' + display_text(proposal['expires_at']))
    native = proposal['display']
    method, params = native['method'], native.get('params', {})
    if key['kind'] == 'native_approval':
        print(display_text(json.dumps(native, ensure_ascii=False, indent=2)))
        choice = input('Approve this exact request? [yes/no/cancel] ').strip().lower()
        if choice not in ('yes', 'no'):
            return None
        return ('approve' if choice == 'yes' else 'deny'), None
    print(display_text(params.get('message') or params.get('title') or method))
    choice = input('Answer this request? [yes/deny/cancel] ').strip().lower()
    if choice == 'deny':
        return 'deny', None
    if choice != 'yes':
        return None
    if method in ('item/tool/requestUserInput', 'control_request:can_use_tool'):
        codex = method == 'item/tool/requestUserInput'
        if not codex and params.get('tool_name') != 'AskUserQuestion':
            raise ConnectionError('QUESTION_UNSUPPORTED', 'This native question form is not supported by the terminal.')
        questions = params.get('questions') if codex else params.get('input', {}).get('questions')
        if not questions:
            raise ConnectionError('QUESTION_UNAVAILABLE', 'The question has no readable fields.')
        answers = {}
        for question in questions:
            print(display_text(question['question']))
            options = question.get('options') or []
            for option in options:
                if option.get('description'):
                    print(display_text(option['label'] + ': ' + option['description']))
            texts = _select([item['label'] for item in options], multiple=codex or question.get('multiSelect', False),
                            other=not codex or question.get('isOther', False)) if options else [input('Your answer: ')]
            if not all(texts):
                raise ConnectionError('ANSWER_REQUIRED', 'Answer each question before sending.')
            answers[question['id'] if codex else question['question']] = (
                {'answers': texts} if codex else texts if question.get('multiSelect') else texts[0])
        response = {'answers': answers}
    elif method == 'extension_ui_request':
        variant = params['method']
        if variant == 'select':
            response = {'value': _select(params['options'])[0]}
        elif variant == 'confirm':
            choice = input('Confirm? [yes/no] ').strip().lower()
            if choice not in ('yes', 'no'):
                raise ConnectionError('ANSWER_REQUIRED', 'Choose yes or no explicitly.')
            response = {'confirmed': choice == 'yes'}
        elif variant in ('input', 'editor'):
            response = {'value': input('Your answer: ')}
        else:
            raise ConnectionError('QUESTION_UNSUPPORTED', 'This native question form is not supported by the terminal.')
    elif method == 'mcpServer/elicitation/request' and params.get('mode', 'form') == 'form':
        schema = params['requestedSchema']
        content = {}
        for name, prop in schema.get('properties', {}).items():
            print(display_text(prop.get('title') or name))
            if prop.get('description'):
                print(display_text(prop['description']))
            if name not in schema.get('required', []):
                if input('Include this optional field? [yes/no] ').strip().lower() != 'yes':
                    continue
            if 'enum' in prop:
                labels = [json.dumps(value, ensure_ascii=False) for value in prop['enum']]
                value = prop['enum'][labels.index(_select(labels)[0])]
            elif prop['type'] == 'boolean':
                choice = input('Value [true/false]: ').strip().lower()
                if choice not in ('true', 'false'):
                    raise ConnectionError('ANSWER_REQUIRED', 'Choose true or false explicitly.')
                value = choice == 'true'
            elif prop['type'] in ('integer', 'number'):
                try:
                    raw = input('Value: ')
                    value = int(raw) if prop['type'] == 'integer' else float(raw)
                    if not math.isfinite(value):
                        raise ValueError
                except ValueError:
                    raise ConnectionError('ANSWER_REQUIRED', 'Enter a finite number of the requested type.') from None
            elif prop['type'] == 'string':
                value = input('Value (empty text is explicit): ')
            else:
                raise ConnectionError('QUESTION_UNSUPPORTED', 'This field type is not supported by the terminal.')
            content[name] = value
        response = {'content': content}
    else:
        raise ConnectionError('QUESTION_UNSUPPORTED', 'This native request cannot be answered in the terminal form.')
    if len(json.dumps(response, ensure_ascii=False).encode('utf-8')) > 16384:
        raise ConnectionError('ANSWER_TOO_LARGE', 'The answer exceeds the native response limit.')
    return 'approve', response
