import subprocess

subprocess.run(["git", "config", "user.name", "Claude Opus 4"])
subprocess.run(["git", "config", "user.email", "claude_opus4@ps-tech.com"])

subprocess.run(["git", "add", "05_검증_리뷰/Phase9_기술서_v2_리뷰검증.md", "ps-docparser/tests/golden/", "폴더정리_및_Git_셋업_기록_20260420.md"])
subprocess.run(["git", "commit", "-m", "chore(test): setup golden snapshot before phase9"])
subprocess.run(["git", "tag", "phase9-baseline"])
