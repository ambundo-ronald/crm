"""Three-way field comparison; CRM workflow fields are excluded by the caller."""


def merge_changes(incoming, previous_source, current_target, previous_target):
	changes, conflicts = {}, []
	for field, value in incoming.items():
		if value == previous_source.get(field, ""):
			continue
		current = current_target.get(field, "")
		if current != previous_target.get(field, "") and current != value:
			conflicts.append(field)
		elif current != value:
			changes[field] = value
	return changes, sorted(conflicts)
