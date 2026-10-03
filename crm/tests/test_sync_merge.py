import unittest

from crm.migration.sync_merge import merge_changes


class TestSyncMerge(unittest.TestCase):
	def test_unchanged_source_preserves_local_edit(self):
		self.assertEqual(
			merge_changes({"phone": "a"}, {"phone": "a"}, {"phone": "local"}, {"phone": "a"}), ({}, [])
		)

	def test_change_and_explicit_clear(self):
		self.assertEqual(
			merge_changes({"phone": ""}, {"phone": "a"}, {"phone": "a"}, {"phone": "a"}), ({"phone": ""}, [])
		)

	def test_divergent_edits_conflict(self):
		self.assertEqual(
			merge_changes({"phone": "source"}, {"phone": "a"}, {"phone": "local"}, {"phone": "a"}),
			({}, ["phone"]),
		)

	def test_convergent_edits_succeed(self):
		self.assertEqual(
			merge_changes({"phone": "b"}, {"phone": "a"}, {"phone": "b"}, {"phone": "a"}), ({}, [])
		)
