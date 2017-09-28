#!/usr/bin/env python
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Authors:
# - Wen Guan, wen.guan@cern.ch, 2017


import json
import logging
import Queue
import subprocess
import sys
import threading
import time
import unittest

from pilot.eventservice.eshook import ESHook
from pilot.eventservice.esmanager import ESManager
from pilot.eventservice.esmessage import MessageThread
from pilot.eventservice.esprocess import ESProcess

logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)


class TestESHook(ESHook):
    """
    A class implemented ESHook, to be used to test eventservice.
    """

    def __init__(self):
        with open('pilot/test/resource/eventservice_job.txt') as job_file:
            job = json.load(job_file)
            self.__payload = job['payload']
            self.__event_ranges = job['event_ranges']

        process = subprocess.Popen('pilot/test/resource/download_test_es_evgen.sh', shell=True, stdout=subprocess.PIPE)
        process.wait()
        if process.returncode != 0:
            raise Exception('failed to download input files for es test: %s %s' % (process.communicate()))

        self.__injected_event_ranges = []
        self.__outputs = []

    def get_payload(self):
        """
        returns: dict {'payload': <cmd string>, 'output_file': <filename or without it>, 'error_file': <filename or without it>}
        """

        return self.__payload

    def get_event_ranges(self, num_ranges=1):
        """
        returns: dict of event ranges.
                 None if no available events.
        """
        ret = []
        for _ in range(num_ranges):
            if len(self.__event_ranges) > 0:
                event_range = self.__event_ranges.pop(0)
                ret.append(event_range)
                self.__injected_event_ranges.append(event_range)
        return ret

    def handle_out_message(self, message):
        """
        Handle ES out message.

        :param message: a dict of parsed message.
                        For 'finished' event ranges, it's {'id': <id>, 'status': 'finished', 'output': <output>, 'cpu': <cpu>,
                                                           'wall': <wall>, 'message': <full message>}.
                        Fro 'failed' event ranges, it's {'id': <id>, 'status': 'finished', 'message': <full message>}.
        """

        print(message)
        self.__outputs.append(message)

    def get_injected_event_ranges(self):
        return self.__injected_event_ranges

    def get_outputs(self):
        return self.__outputs


class TestESMessageThread(unittest.TestCase):
    """
    Unit tests for event service message thread.
    """

    def test_msg_thread(self):
        """
        Make sure that es message thread works as expected.
        """
        queue = Queue.Queue()
        msgThread = MessageThread(queue, socket_name='test', context='local')
        self.assertIsInstance(msgThread, threading.Thread)

        msgThread.start()
        time.sleep(1)
        self.assertTrue(msgThread.is_alive())

        msgThread.send('test')
        msgThread.stop()
        self.assertTrue(msgThread.stopped())
        time.sleep(1)
        self.assertFalse(msgThread.is_alive())


class TestESProcess(unittest.TestCase):
    """
    Unit tests for event service process functions
    """

    @classmethod
    def setUpClass(cls):
        cls._testHook = TestESHook()
        cls._esProcess = ESProcess(cls._testHook.get_payload())

    def test_set_get_event_ranges_hook(self):
        """
        Make sure that no exceptions to set get_event_ranges hook.
        """

        self._esProcess.set_get_event_ranges_hook(self._testHook.get_event_ranges)
        self.assertEqual(self._testHook.get_event_ranges, self._esProcess.get_get_event_ranges_hook())

    def test_set_handle_out_message_hook(self):
        """
        Make sure that no exceptions to set handle_out_message hook.
        """

        self._esProcess.set_handle_out_message_hook(self._testHook.handle_out_message)
        self.assertEqual(self._testHook.handle_out_message, self._esProcess.get_handle_out_message_hook())

    def test_parse_out_message(self):
        """
        Make sure to parse messages from payload correctly.
        """

        output_msg = '/tmp/HITS.12164365._000300.pool.root.1.12164365-3616045203-10980024041-4138-8,ID:12164365-3616045203-10980024041-4138-8,CPU:288,WALL:303'
        ret = self._esProcess.parse_out_message(output_msg)
        self.assertEqual(ret['status'], 'finished')
        self.assertEqual(ret['id'], '12164365-3616045203-10980024041-4138-8')

        error_msg1 = 'ERR_ATHENAMP_PROCESS 130-2068634812-21368-1-4: Failed to process event range'
        ret = self._esProcess.parse_out_message(error_msg1)
        self.assertEqual(ret['status'], 'failed')
        self.assertEqual(ret['id'], '130-2068634812-21368-1-4')

        error_msg2 = "ERR_ATHENAMP_PARSE \"u'LFN': u'eta0-25.evgen.pool.root',u'eventRangeID': u'130-2068634812-21368-1-4', u'startEvent': 5\": Wrong format"
        ret = self._esProcess.parse_out_message(error_msg2)
        self.assertEqual(ret['status'], 'failed')
        self.assertEqual(ret['id'], '130-2068634812-21368-1-4')


class TestEventService(unittest.TestCase):
    """
    Unit tests for event service functions.
    """

    def test_init_esmanager(self):
        """
        Make sure that no exceptions to init ESManager
        """
        testHook = TestESHook()
        esManager = ESManager(testHook)
        self.assertIsInstance(esManager, ESManager)

    def test_run_es(self):
        """
        Make sure that ES produced all events that injected.
        """
        testHook = TestESHook()
        esManager = ESManager(testHook)
        esManager.run()
        injected_event = testHook.get_injected_event_ranges()
        outputs = testHook.get_outputs()

        self.assertEqual(len(injected_event), len(outputs))
        self.assertNotEqual(len(outputs), 0)
