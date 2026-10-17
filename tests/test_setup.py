from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import unittest
from unittest.mock import patch

from dotenv import dotenv_values
from ingest.configure_local import configure


class SetupTests(unittest.TestCase):
    def test_read_only_setup_preserves_model_key_and_hides_password(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.env.example').write_text('DB_DSN=host=127.0.0.1 user=postgres\n')
            (root / '.env').write_text('OPENAI_API_KEY=local-test-placeholder\nDB_DSN=host=127.0.0.1 user=postgres\n')
            with patch('ingest.configure_local.subprocess.run') as run, patch('builtins.print') as output:
                configure('test-container', 7891, root)
            sql = run.call_args.kwargs['input']
            for table in ['logs', 'templates', 'ownership']:
                self.assertIn(f'GRANT SELECT ON {table} TO log_observatory;', sql)
            self.assertNotIn('ON logs,', sql)
            self.assertNotIn('SUPERUSER', sql)
            self.assertNotIn('SET hba', sql)
            self.assertIn('test-container', run.call_args.args[0])
            config = dotenv_values(root / '.env')
            self.assertEqual(config['OPENAI_API_KEY'], 'local-test-placeholder')
            self.assertIn('port=7891', config['DB_DSN'])
            password = config['DB_DSN'].split('password=')[1]
            self.assertNotIn(password, str(output.call_args))
            with patch('ingest.configure_local.subprocess.run') as run, self.assertRaises(ValueError):
                configure(root=root)
            run.assert_not_called()

    def test_failed_database_setup_does_not_write_env(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.env.example').write_text('DB_DSN=host=127.0.0.1 user=postgres\n')
            with patch('ingest.configure_local.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'docker')):
                with self.assertRaises(subprocess.CalledProcessError):
                    configure(root=root)
            self.assertFalse((root / '.env').exists())
