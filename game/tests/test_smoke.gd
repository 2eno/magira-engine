extends GutTest
## Rauchtest: stellt sicher, dass GUT in der CI wirklich Tests findet und ausführt.


func test_gut_runs() -> void:
	assert_true(true, "GUT läuft")
