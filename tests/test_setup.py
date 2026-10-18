from pathlib import Path
import os
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
            self.assertTrue(sql.startswith('BEGIN;'))
            self.assertTrue(sql.rstrip().endswith('COMMIT;'))
            self.assertFalse((root / '.env.setup').exists())
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
            self.assertIn('user=log_observatory', dotenv_values(root / '.env.setup')['DB_DSN'])
            with patch('ingest.configure_local.subprocess.run') as run, self.assertRaisesRegex(ValueError, 'recoverable credentials'):
                configure(root=root)
            run.assert_not_called()

    def test_configuration_write_failure_happens_before_database_changes(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.env.example').write_text('DB_DSN=host=127.0.0.1 user=postgres\n')
            with patch('ingest.configure_local.set_key', side_effect=OSError('disk full')), patch('ingest.configure_local.subprocess.run') as run:
                with self.assertRaises(OSError):
                    configure(root=root)
            run.assert_not_called()

    def test_final_rename_failure_preserves_credentials_and_existing_env(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            original = 'DB_DSN=host=127.0.0.1 user=postgres\nOPENAI_API_KEY=placeholder\n'
            (root / '.env.example').write_text(original)
            (root / '.env').write_text(original)
            replace = os.replace
            def fail_final_rename(source, target):
                if Path(target) == root / '.env':
                    raise OSError('locked')
                return replace(source, target)
            with patch('ingest.configure_local.subprocess.run') as run, patch('ingest.configure_local.os.replace', side_effect=fail_final_rename):
                with self.assertRaises(OSError):
                    configure(root=root)
            self.assertEqual((root / '.env').read_text(), original)
            saved = dotenv_values(root / '.env.setup')
            password = saved['DB_DSN'].split('password=')[1]
            self.assertIn(f"PASSWORD '{password}'", run.call_args.kwargs['input'])
            self.assertEqual(saved['OPENAI_API_KEY'], 'placeholder')


class SqlLoaderTests(unittest.TestCase):
    def test_loader_uses_container_admin_and_propagates_failure(self):
        from ingest.run_sql import main
        with TemporaryDirectory() as folder:
            sql = Path(folder) / 'load.sql'
            sql.write_text('SELECT 1; SELECT nonexistent; SELECT 2;')
            with patch('ingest.run_sql.subprocess.run', side_effect=subprocess.CalledProcessError(3, 'psql')) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    main(str(sql))
            self.assertIn('ON_ERROR_STOP=1', run.call_args.args[0])
            self.assertIn('serenedb', run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs['input'], sql.read_text())
            self.assertTrue(run.call_args.kwargs['check'])
