"""Operator-only explicit enqueue/status CLI; no network fetch or scheduler."""
import argparse
import json


def main(argv=None):
    parser = argparse.ArgumentParser(description='Operator connector queue control')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--source', help='Approved source ID; current UTC hour only')
    group.add_argument('--status', help='Connector job UUID')
    args = parser.parse_args(argv)
    database = None
    try:
        from app.database.backend import Database
        from app.database.config import load_database_settings
        from app.jobs import JobRepository, JobService, load_job_settings
        from app.monitoring.config import load_monitoring_settings
        from .catalog import build_source_catalog
        from .ingestion import ConnectorSyncService, connector_version, sync_window, validate_payload
        catalog = build_source_catalog(load_monitoring_settings())
        if args.source:
            validate_payload({'schema': 1, 'source_id': args.source, 'sync_window': sync_window(),
                              'connector_version': connector_version(args.source)}, catalog.registry)
        database = Database(load_database_settings())
        repository = JobRepository(database, load_job_settings())
        repository.initialize()
        service = ConnectorSyncService(JobService(repository), catalog)
        if args.source:
            job = service.enqueue(args.source)
            output = {'job_id': job.id, 'state': job.state}
        else:
            output = service.status(args.status)
            if output is None:
                raise ValueError('Not found.')
        print(json.dumps(output, separators=(',', ':')))
        return 0
    except Exception:
        print('Connector queue operation failed; verify approved source/configuration.')
        return 2
    finally:
        if database is not None:
            database.close()


if __name__ == '__main__':
    raise SystemExit(main())
