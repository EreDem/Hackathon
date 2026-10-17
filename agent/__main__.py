"""Terminal-Einstieg: python -m agent --rolle Engineer --frage '...'"""
import argparse
import json

from agent.agent import antworte

parser = argparse.ArgumentParser(description="Log-Agent: Frage, Belege und Empfehlung")
parser.add_argument("--rolle", choices=["Engineer", "Team Lead", "Manager"], default="Engineer")
parser.add_argument("--team", default=None)
parser.add_argument("--frage", required=True)
args = parser.parse_args()
result = antworte(args.rolle, args.team, args.frage, [])
print(result["text"])
print(json.dumps({"belege": result["belege"], "meta": result["meta"]}, ensure_ascii=False, indent=2))
