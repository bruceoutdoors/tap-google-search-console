import unittest
import os
from datetime import timedelta
from datetime import datetime as dt
import time

import singer
from tap_tester import connections, menagerie, runner

class GoogleSearchConsoleBaseTest(unittest.TestCase):
    """
    Setup expectations for test sub classes.
    Metadata describing streams.
    A bunch of shared methods that are used in tap-tester tests.
    Shared tap-specific methods (as needed).
    """
    AUTOMATIC_FIELDS = "automatic"
    REPLICATION_KEYS = "valid-replication-keys"
    PRIMARY_KEYS = "table-key-properties"
    REPLICATION_METHOD = "forced-replication-method"
    INCREMENTAL = "INCREMENTAL"
    FULL_TABLE = "FULL_TABLE"
    START_DATE_FORMAT = "%Y-%m-%dT00:00:00Z"
    DATETIME_FMT = {
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.000000Z"
    }
    start_date = ""
    properties = {
        "client_id": "TAP_GOOGLE_SEARCH_CONSOLE_CLIENT_ID",
	"site_urls": "TAP_GOOGLE_SEARCH_CONSOLE_SITE_URLS"
    }
    credentials = {
        "client_secret": "TAP_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET",
        "refresh_token": "TAP_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN"
    }


    @staticmethod
    def tap_name():
        """The name of the tap"""
        return 'tap-google-search-console'

    @staticmethod
    def get_type():
        return 'platform.google-search-console'

    def get_properties(self, original: bool = True):
        """Configuration properties required for the tap."""
        properties_dict = {
            'start_date': dt.strftime(dt.utcnow()-timedelta(days=14), self.START_DATE_FORMAT),
        }
        props = self.properties
        for prop in props:
            properties_dict[prop] = os.getenv(props[prop])

        if original:
            return properties_dict

        properties_dict["start_date"] = self.start_date
        return properties_dict

    def get_credentials(self):
        """Authentication information for the test account. Username is expected as a property."""
        credentials_dict = {}
        creds = self.credentials
        for cred in creds:
            credentials_dict[cred] = os.getenv(creds[cred])

        return credentials_dict

    def expected_metadata(self):
        """The expected primary key of the streams"""
        return{
            "sites": {
                self.PRIMARY_KEYS: {"site_url"},
                self.REPLICATION_METHOD: self.FULL_TABLE,
            },
            "sitemaps": {
                self.PRIMARY_KEYS: {"site_url", "path", "last_submitted"},
                self.REPLICATION_METHOD: self.FULL_TABLE,
            },
            "performance_report_custom": {
                self.PRIMARY_KEYS: {"site_url", "search_type", "date", "dimensions_hash_key"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"date"}
            },
            "performance_report_date": {
                self.PRIMARY_KEYS: {"site_url", "search_type", "date"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"date"}
            },
            "performance_report_country": {
                self.PRIMARY_KEYS: {"site_url", "search_type", "date", "country"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"date"}
            },
            "performance_report_device": {
                self.PRIMARY_KEYS: {"site_url", "search_type", "date", "device"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"date"}
            },
            "performance_report_page": {
                self.PRIMARY_KEYS: {"site_url", "search_type", "date", "page"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"date", "page"}
            },
            "performance_report_query": {
                self.PRIMARY_KEYS: {"site_url", "search_type", "date", "query"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"date"}
            }
        }

    def expected_streams(self):
        """A set of expected stream names"""
        return set(self.expected_metadata().keys())

    def expected_primary_keys(self):
        """return a dictionary with key of table name and value as a set of primary key fields"""
        return {table: properties.get(self.PRIMARY_KEYS, set())
                for table, properties
                in self.expected_metadata().items()}

    def expected_replication_keys(self):
        """return a dictionary with key of table name and value as a set of replication key fields"""
        return {table: properties.get(self.REPLICATION_KEYS, set())
                for table, properties
                in self.expected_metadata().items()}

    def expected_automatic_fields(self):
        """return a dictionary with key of table name and set of value of automatic(primary key and bookmark field) fields"""
        auto_fields = {}
        for k, v in self.expected_metadata().items():
            auto_fields[k] = v.get(self.PRIMARY_KEYS, set()) |  v.get(self.REPLICATION_KEYS, set())
        return auto_fields

    def expected_replication_method(self):
        """return a dictionary with key of table name and value of replication method"""
        return {table: properties.get(self.REPLICATION_METHOD, None)
                for table, properties
                in self.expected_metadata().items()}

    def setUp(self):
        missing_envs = []
        props = self.properties
        creds = self.credentials

        for prop in props:
            if os.getenv(props[prop]) == None:
                missing_envs.append(prop)
        for cred in creds:
            if os.getenv(creds[cred]) == None:
                missing_envs.append(cred)

        if len(missing_envs) != 0:
            raise Exception("set " + ", ".join(missing_envs))

    #########################
    #   Helper Methods      #
    #########################

    def run_and_verify_check_mode(self, conn_id):
        """
        Run the tap in check mode and verify it succeeds.
        This should be ran prior to field selection and initial sync.
        Return the connection id and found catalogs from menagerie.
        """
        # run in check mode
        check_job_name = runner.run_check_mode(self, conn_id)

        # verify check exit codes
        exit_status = menagerie.get_exit_status(conn_id, check_job_name)
        menagerie.verify_check_exit_status(self, exit_status, check_job_name)

        found_catalogs = menagerie.get_catalogs(conn_id)
        self.assertGreater(len(found_catalogs), 0, msg="unable to locate schemas for connection {}".format(conn_id))

        found_catalog_names = set(map(lambda c: c['stream_name'], found_catalogs))
        print(found_catalog_names)
        self.assertSetEqual(self.expected_streams(), found_catalog_names, msg="discovered schemas do not match")
        print("discovered schemas are OK")

        return found_catalogs

    def run_and_verify_sync(self, conn_id):
        """
        Run a sync job and make sure it exited properly.
        Return a dictionary with keys of streams synced
        and values of records synced for each stream
        """
        # Run a sync job using orchestrator
        sync_job_name = runner.run_sync_mode(self, conn_id)

        # Verify tap and target exit codes
        exit_status = menagerie.get_exit_status(conn_id, sync_job_name)
        menagerie.verify_sync_exit_status(self, exit_status, sync_job_name)

        # Verify actual rows were synced
        sync_record_count = runner.examine_target_output_file(
            self, conn_id, self.expected_streams(), self.expected_primary_keys())
        self.assertGreater(
            sum(sync_record_count.values()), 0,
            msg="failed to replicate any data: {}".format(sync_record_count)
        )
        print("total replicated row count: {}".format(sum(sync_record_count.values())))

        return sync_record_count

    def perform_and_verify_table_and_field_selection(self,
                                                     conn_id,
                                                     test_catalogs,
                                                     select_all_fields=True):
        """
        Perform table and field selection based off of the streams to select
        set and field selection parameters.
        Verify this results in the expected streams selected and all or no
        fields selected for those streams.
        """

        # Select all available fields or select no fields from all testable streams
        self.select_all_streams_and_fields(
            conn_id=conn_id, catalogs=test_catalogs, select_all_fields=select_all_fields
        )

        catalogs = menagerie.get_catalogs(conn_id)

        # Ensure our selection affects the catalog
        expected_selected = [tc.get('stream_name') for tc in test_catalogs]
        for cat in catalogs:
            catalog_entry = menagerie.get_annotated_schema(conn_id, cat['stream_id'])

            # Verify all testable streams are selected
            selected = catalog_entry.get('annotated-schema').get('selected')
            print("Validating selection on {}: {}".format(cat['stream_name'], selected))
            if cat['stream_name'] not in expected_selected:
                self.assertFalse(selected, msg="Stream selected, but not testable.")
                continue # Skip remaining assertions if we aren't selecting this stream
            self.assertTrue(selected, msg="Stream not selected.")

            if select_all_fields:
                # Verify all fields within each selected stream are selected
                for field, field_props in catalog_entry.get('annotated-schema').get('properties').items():
                    field_selected = field_props.get('selected')
                    print("\tValidating selection on {}.{}: {}".format(
                        cat['stream_name'], field, field_selected))
                    self.assertTrue(field_selected, msg="Field not selected.")
            else:
                # Verify only automatic fields are selected
                expected_automatic_fields = self.expected_automatic_fields().get(cat['stream_name'])
                selected_fields = self.get_selected_fields_from_metadata(catalog_entry['metadata'])
                self.assertEqual(expected_automatic_fields, selected_fields)

    @staticmethod
    def get_selected_fields_from_metadata(metadata):
        selected_fields = set()
        for field in metadata:
            is_field_metadata = len(field['breadcrumb']) > 1
            inclusion_automatic_or_selected = (
                field['metadata']['selected'] is True or \
                field['metadata']['inclusion'] == 'automatic'
            )
            if is_field_metadata and inclusion_automatic_or_selected:
                selected_fields.add(field['breadcrumb'][1])
        return selected_fields


    @staticmethod
    def select_all_streams_and_fields(conn_id, catalogs, select_all_fields: bool = True):
        """Select all streams and all fields within streams"""
        for catalog in catalogs:
            schema = menagerie.get_annotated_schema(conn_id, catalog['stream_id'])

            non_selected_properties = []
            if not select_all_fields:
                # get a list of all properties so that none are selected
                non_selected_properties = schema.get('annotated-schema', {}).get(
                    'properties', {}).keys()

            connections.select_catalog_and_fields_via_metadata(
                conn_id, catalog, schema, [], non_selected_properties)

    def timedelta_formatted(self, dtime, days=0):
        date_stripped = dt.strptime(dtime, self.START_DATE_FORMAT)
        return_date = date_stripped + timedelta(days=days)

        return dt.strftime(return_date, self.START_DATE_FORMAT)

    ##########################################################################
    ### Tap Specific Methods
    ##########################################################################

    def is_incremental(self, stream):
        return self.expected_metadata()[stream][self.REPLICATION_METHOD] == self.INCREMENTAL

    def dt_to_ts(self, dtime):
        for date_format in self.DATETIME_FMT:
            try:
                date_stripped = int(time.mktime(dt.strptime(dtime, date_format).timetuple()))
                return date_stripped
            except ValueError:
                continue
