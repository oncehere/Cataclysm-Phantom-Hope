# `tests/` agent instructions

- Prefer a focused regression test that fails before the fix and passes after.
- Keep tests deterministic; print or record the RNG seed when randomness is
  relevant.
- Reuse test helpers and fixtures instead of introducing production-only test
  branches.
- Match the subsystem's ownership and cleanup patterns.

For C++/Catch2 tests:

```sh
make -j2 tests
./tests/cata_test "<focused test filter>"
```

For Python project automation under `tests/project/`:

```sh
python3 -m unittest discover -s tests/project -p 'test_*.py'
```

Python lint is a separate check and does not replace these behaviour tests.

测试应能证明行为变化，而不只是覆盖新代码行；随机测试必须可复现。
