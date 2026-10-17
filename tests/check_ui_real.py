"""UI acceptance against the real corpus; paid model calls require --live.

python -m tests.check_ui_real
python -m tests.check_ui_real --live
Evidence is saved to ignored out/ui-validation.json, never to the repository.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from streamlit.testing.v1 import AppTest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Run one paid, English agent investigation per UI role')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = {'created': datetime.now(timezone.utc).isoformat(), 'live': args.live, 'roles': []}
    app = AppTest.from_file(str(root / 'app.py'), default_timeout=180)

    def button(label):
        return next(b for b in app.button if b.label == label)

    def select(label):
        return next(b for b in app.selectbox if b.label == label)

    try:
        app.run()
        assert not app.exception, 'UI startup failed'
        assert app.session_state['scope'] is not None, 'Database is unavailable to the UI'
        total = sum(r['logzeilen_gesamt'] for r in app.session_state['catalog']['daten'])
        assert total == 4955783, 'Load both full challenge datasets first'
        report['corpus_rows'] = total
        for role in ['Engineer', 'Team Lead', 'Manager']:
            select('Your perspective').select(role).run()
            if role == 'Team Lead':
                select('Ownership team').select('HPC Kernel')
                button('Apply scope').click().run()
            button('Run prepared investigation').click().run()
            if role == 'Engineer':
                button('Map all matching logs').click().run()
                assert app.session_state['results']['distribution']['daten']
                select('Inspect a resource/time cell').select(0).run()
                button('Open resource event lens').click().run()
                assert app.session_state['results']['context']['daten']
            elif role == 'Team Lead':
                button('Compare leading patterns').click().run()
                assert 'comparison_0' in app.session_state['results']
            else:
                button('Compare teams and periods').click().run()
                assert len(app.session_state['results']['period_comparison']['daten']) == 2
            assert not app.exception and not app.error, f'{role}: direct exploration failed'
            entry = {'role': role, 'scope': app.session_state['scope'],
                     'direct_evidence': list(app.session_state['records'].values())}
            report['roles'].append(entry)
            if args.live:
                assert not app.chat_input[0].disabled, 'Configure OPENAI_API_KEY in the local .env'
                button('Ask the prepared question').click().run()
                assert not app.exception and not app.error, f'{role}: UI request failed'
                issue = app.session_state['agent_issue']
                if issue:
                    entry['agent'] = issue
                    raise AssertionError(f"{role}: agent status {issue['meta'].get('status')}")
                answer = app.session_state['conversation'][-1]
                entry['agent'] = answer
                assert answer['meta']['status'] == 'ok', f'{role}: incomplete agent result'
                assert answer['evidence'], f'{role}: missing executed evidence'
                assert '[B' in answer['content'], f'{role}: missing evidence references'
                print(f"OK {role}: {answer['meta']['tool_aufrufe']} tool calls; estimated ${answer['meta']['kosten_usd_geschaetzt']:.5f}", flush=True)
            else:
                print(f'OK {role}: direct live-data UI', flush=True)
        report['passed'] = True
    except Exception as exc:
        report['passed'] = False
        report['error'] = str(exc)
        raise
    finally:
        path = root / 'out' / 'ui-validation.json'
        path.write_text(json.dumps(report, default=str, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Evidence: {path}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
