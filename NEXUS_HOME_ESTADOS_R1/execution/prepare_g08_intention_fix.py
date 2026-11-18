"""Apply the G08 label delta only in the dedicated detached UI worktree."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
tree = Path(json.loads((HERE / 'g08-ui-worktree-allocation.json').read_text())['root'])
assert tree.name.startswith('nexus-hst-ui-intent-') and tree.parent.name == 'Temp'
path = tree / 'frontend/src/components/MetaHarnessComposer.tsx'
text = path.read_text(encoding='utf-8')
changes = {
    'aria-label="Delivery type"': 'role="group" aria-label="Interaction"',
    'testId="meta-kind-message">Message</ChoiceButton>': 'testId="meta-kind-message">Chat</ChoiceButton>',
    'testId="meta-kind-handoff">Handoff</ChoiceButton>': 'testId="meta-kind-handoff">Ask for work</ChoiceButton>',
    'aria-label="Send namespace"': 'aria-label="Project for this interaction"',
    'title="Namespaces available for the selected agent"': 'title="Projects available for the selected agent"',
    '"Could not load namespaces" : !namespacesReady ? "Loading namespaces…" : "No namespace available"':
        '"Could not load projects" : !namespacesReady ? "Loading projects…" : "No project available"',
    'aria-label="Send turn"': 'aria-label={kind === "handoff" ? "Ask for work" : "Send chat message"}',
}
for old, new in changes.items():
    assert text.count(old) == 1, old
    text = text.replace(old, new)
path.write_text(text, encoding='utf-8')
tests = tree / 'frontend/tests/homeUI.test.mjs'
text = tests.read_text(encoding='utf-8')
text = text.replace("test('shared composer exposes explicit message versus handoff without a hidden chosen recipient'",
                    "test('shared composer uses intention labels and requires an explicit recipient'")
old = '  assert.match(markup,/<button[^>]*disabled=""[^>]*aria-label="Send turn"/);'
new = '''  assert.match(markup,/role="group" aria-label="Interaction"/);
  assert.match(markup,/meta-kind-message[^>]*aria-pressed="true"[^]*?>Chat<\\/button>/);
  assert.match(markup,/meta-kind-handoff[^]*?>Ask for work<\\/button>/);
  assert.match(markup,/<button[^>]*disabled=""[^>]*aria-label="Send chat message"/);'''
assert text.count(old) == 1
tests.write_text(text.replace(old, new), encoding='utf-8')
print(tree)
