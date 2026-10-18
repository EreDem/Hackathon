"""Create the local read-only app login after loading a fresh Docker database.

python ingest/configure_local.py
Credentials are staged in ignored .env.setup before replacing .env.
Existing configured credentials are preserved.
"""
import argparse
import os
from pathlib import Path
import secrets
import subprocess

from dotenv import dotenv_values, set_key


def configure(container='serenedb', port=7890, root=Path('.')):
    if not 1 <= port <= 65535:
        raise ValueError('Port must be between 1 and 65535.')
    env = root / '.env'
    pending = root / '.env.setup'
    if pending.exists():
        raise ValueError('A previous setup left .env.setup with recoverable credentials. If database setup succeeded, replace .env with .env.setup; otherwise remove .env.setup and retry. Keep both files private.')
    existing = dotenv_values(env).get('DB_DSN') if env.exists() else None
    default = dotenv_values(root / '.env.example').get('DB_DSN')
    if existing and existing != default:
        raise ValueError('An app connection is already configured. Preserve .env; do not rotate credentials during setup.')
    password = secrets.token_hex(24)
    sql = f"""BEGIN;
CREATE ROLE log_observatory LOGIN PASSWORD '{password}';
GRANT USAGE ON SCHEMA public TO log_observatory;
GRANT SELECT ON logs TO log_observatory;
GRANT SELECT ON templates TO log_observatory;
GRANT SELECT ON ownership TO log_observatory;
COMMIT;
"""
    # Stage credentials before creating the login so a failed final rename cannot lose them.
    pending.write_text((env if env.exists() else root / '.env.example').read_text(encoding='utf-8'), encoding='utf-8')
    set_key(str(pending), 'DB_DSN', f'host=127.0.0.1 port={port} dbname=postgres user=log_observatory password={password}')
    subprocess.run(['docker', 'exec', '-i', container, 'psql', '-h', '127.0.0.1',
                    '-p', '7890', '-U', 'postgres', '-v', 'ON_ERROR_STOP=1'],
                   input=sql, text=True, check=True, capture_output=True)
    os.replace(pending, env)
    print('Read-only app connection saved to .env. No credential was printed. Keep .env private.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', default='serenedb')
    parser.add_argument('--port', type=int, default=7890)
    args = parser.parse_args()
    try:
        configure(args.container, args.port)
    except subprocess.CalledProcessError:
        parser.exit(1, 'Local login setup failed. Existing .env was preserved. Credentials remain in ignored .env.setup: check whether log_observatory exists before retrying. If absent, remove .env.setup and retry; if setup committed, replace .env with .env.setup.\n')
    except OSError:
        parser.exit(1, 'Could not save local configuration. Existing .env was preserved; check .env.setup for recoverable credentials before retrying.\n')
    except ValueError as exc:
        parser.exit(1, f'{exc}\n')
