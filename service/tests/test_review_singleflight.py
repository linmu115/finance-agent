"""No model/API calls: concurrency and ownership contracts on real SQLite."""
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
from pathlib import Path

from service.review_cache import shared_result


class TestStore:
    def __init__(self,path):self.path=Path(path)
    @contextmanager
    def connect(self,write=False):
        db=sqlite3.connect(self.path,timeout=5)
        try:
            with db:yield db
        finally:db.close()


class SharedReviewInferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=TestStore(Path(self.tmp.name)/"review.sqlite")
        with self.store.connect(True) as db:
            db.execute("CREATE TABLE temporal_review_cache(cache_key TEXT PRIMARY KEY,result_json TEXT,created_at TEXT)")
    def call(self,infer,cancelled=lambda:False,key="same"):
        return shared_result(self.store,"temporal_review_cache",{"cache_key":key},infer,cancelled)
    def payload(self,owner):return {"_review_provenance":{"owner_run_id":owner},"corrections":[owner]}
    def test_one_model_call_and_original_owner_with_two_concurrent_consumers(self):
        entered=threading.Event();release=threading.Event();calls=[]
        def first():
            calls.append("first");entered.set();self.assertTrue(release.wait(5));return self.payload("first"),2
        def second():calls.append("second");return self.payload("second"),1
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(self.call,first);self.assertTrue(entered.wait(3));b=pool.submit(self.call,second)
            with self.assertRaises(TimeoutError):b.result(.05)
            release.set();left,right=a.result(5),b.result(5)
        self.assertEqual(calls,["first"]);self.assertEqual(left,(self.payload("first"),False,2))
        self.assertEqual(right,(self.payload("first"),True,0))
    def test_waiter_cancellation_does_not_cancel_owner(self):
        entered=threading.Event();release=threading.Event();cancel=threading.Event()
        def first():entered.set();release.wait(5);return self.payload("first"),1
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(self.call,first);self.assertTrue(entered.wait(3))
            b=pool.submit(self.call,lambda:self.fail("cancelled waiter cannot infer"),cancel.is_set)
            cancel.set()
            with self.assertRaises(InterruptedError):b.result(3)
            self.assertFalse(a.done());release.set();self.assertEqual(a.result(3)[0],self.payload("first"))
    def test_cancelled_owner_publishes_nothing_waiter_takes_own_runtime(self):
        entered=threading.Event();release=threading.Event();cancel=threading.Event()
        def first():entered.set();release.wait(5);return self.payload("cancelled-owner"),1
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(self.call,first,cancel.is_set);self.assertTrue(entered.wait(3))
            b=pool.submit(self.call,lambda:(self.payload("second-owner"),1))
            with self.assertRaises(TimeoutError):b.result(.05)
            cancel.set()
            result=b.result(3)
            self.assertFalse(a.done(),"the successor need not await cancelled network teardown")
            release.set()
            with self.assertRaises(InterruptedError):a.result(3)
        self.assertEqual(result,(self.payload("second-owner"),False,1))
        with self.store.connect() as db:saved=json.loads(db.execute("SELECT result_json FROM temporal_review_cache").fetchone()[0])
        self.assertEqual(saved,self.payload("second-owner"))
    def test_failed_owner_releases_waiters_and_never_poison_cache(self):
        entered=threading.Event();release=threading.Event()
        def first():entered.set();release.wait(5);raise ValueError("invalid_model_evidence")
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(self.call,first);self.assertTrue(entered.wait(3))
            b=pool.submit(self.call,lambda:(self.payload("successor"),1));release.set()
            with self.assertRaisesRegex(ValueError,"invalid_model_evidence"):a.result(3)
            self.assertEqual(b.result(3),(self.payload("successor"),False,1))
    def test_different_inputs_remain_parallel(self):
        barrier=threading.Barrier(2)
        def infer(owner):barrier.wait(3);return self.payload(owner),1
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(self.call,lambda:infer("a"),key="a")
            b=pool.submit(self.call,lambda:infer("b"),key="b")
            self.assertEqual(a.result(5)[0],self.payload("a"));self.assertEqual(b.result(5)[0],self.payload("b"))
    def test_invalid_result_does_not_enter_cache(self):
        def invalid(_):raise ValueError("coverage_invalid")
        with self.assertRaisesRegex(ValueError,"coverage_invalid"):
            shared_result(self.store,"temporal_review_cache",{"cache_key":"same"},lambda:({},1),validate=invalid)
        with self.store.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM temporal_review_cache").fetchone()[0],0)
        self.assertEqual(self.call(lambda:(self.payload("retry"),1))[0],self.payload("retry"))


if __name__=="__main__":unittest.main()
