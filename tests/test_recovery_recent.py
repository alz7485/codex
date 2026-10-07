import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMessageBox
from e3d_designer.app import Window
from e3d_designer.model import Form,Gadget
from e3d_designer.settings import Settings
from e3d_designer.recovery import RecoveryStore


class RecoveryRecentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.settings_path=self.folder/'settings.json'
        self.w=Window(settings_path=self.settings_path)
        self.other_windows=[]

    def tearDown(self):
        self.app.clipboard().clear()
        for window in [self.w,*self.other_windows]:
            window.dirty=False;window.close()
        self.app.processEvents();self.temp.cleanup()

    def abandoned(self,form=None,source=None,pending=None):
        store=RecoveryStore(self.folder/'recovery')
        store.write(form or Form(title='復元した作業'),source,pending)
        store.lock.unlock()  # Simulate a terminated process without deleting its snapshot.
        return store

    def test_recent_backward_compatibility_limit_persistence_and_output_folder(self):
        self.settings_path.write_text(json.dumps({'version':1,'output_folder':str(self.folder)}))
        settings=Settings(self.settings_path)
        self.assertEqual(settings.recent_files,[])
        for i in range(12):settings.remember_design(self.folder/f'{i}.json')
        settings.remember_design(self.folder/'5.json')
        self.assertEqual(len(settings.recent_files),10)
        self.assertEqual(settings.recent_files[0],str(self.folder/'5.json'))
        self.assertEqual(len(set(settings.recent_files)),10)
        settings.save_output_folder(self.folder)
        restored=Settings(self.settings_path)
        self.assertEqual(restored.recent_files,settings.recent_files)
        self.assertEqual(restored.output_folder,self.folder)
        before=self.settings_path.read_bytes();recent=list(settings.recent_files)
        with patch('e3d_designer.settings.os.replace',side_effect=OSError('read only')):
            with self.assertRaises(OSError):settings.remember_design(self.folder/'failed.json')
        self.assertEqual(settings.recent_files,recent);self.assertEqual(self.settings_path.read_bytes(),before)
        settings.clear_recent();self.assertEqual(Settings(self.settings_path).recent_files,[])

    def test_recent_menu_opens_design_and_missing_file_keeps_current_work(self):
        w=self.w;first=self.folder/'first.json';second=self.folder/'second.json'
        first.write_text(Form(title='First').dumps());second.write_text(Form(title='Second').dumps())
        self.assertTrue(w.open_design(first));self.assertTrue(w.open_design(second))
        self.assertEqual([a.text() for a in w.recent_menu.actions()[:2]],['second.json','first.json'])
        w.recent_menu.actions()[1].trigger();self.assertEqual(w.form.title,'First')
        self.assertEqual(w.settings.recent_files[0],str(first))
        first.unlink();before=w.form.dumps()
        with patch('e3d_designer.app.QMessageBox.warning') as warning:
            w.recent_menu.actions()[0].trigger();warning.assert_called_once()
        self.assertEqual(w.form.dumps(),before);self.assertEqual(w.path,first)
        w.clear_recent();self.assertFalse(w.recent_menu.actions()[0].isEnabled())

    def test_timer_backup_restore_pending_variables_and_explicit_save(self):
        w=self.w;source=self.folder/'design.json';source.write_text(Form(title='Saved').dumps())
        w.form=Form(title='Edited',gadgets=[Gadget(name='run',initial='')]);w.path=source;w.dirty=True;w.refresh()
        w.variables.setPlainText('unfinished variable')
        self.assertTrue(w.variable_error)
        self.assertEqual(w.backup_timer.interval(),30000)
        w.backup_timer.timeout.emit()
        self.assertTrue(w.recovery.path.exists());self.assertEqual(Form.loads(source.read_text()).title,'Saved')
        w.recovery.lock.unlock()
        other=Window(settings_path=self.settings_path);self.other_windows.append(other)
        with patch('e3d_designer.app.QMessageBox.question',return_value=QMessageBox.Yes):other.offer_recovery()
        self.assertEqual(other.form.title,'Edited');self.assertEqual(other.path,source)
        self.assertTrue(other.dirty);self.assertTrue(other.variable_error)
        self.assertEqual(other.variables.toPlainText(),'unfinished variable')
        self.assertEqual(other.history,[]);self.assertEqual(other.future,[])
        self.assertEqual(Form.loads(source.read_text()).title,'Saved')
        other.variables.setPlainText('flag=A');self.assertTrue(other.save())
        self.assertEqual(Form.loads(source.read_text()).title,'Edited')
        self.assertFalse(other.recovery.path.exists());self.assertFalse(w.recovery.path.exists())

    def test_live_sessions_are_excluded_and_declined_recovery_is_retained(self):
        live=RecoveryStore(self.folder/'recovery');live.write(Form(title='Live'))
        self.assertEqual(self.w.recovery_options(),[])
        live.lock.unlock()
        with patch('e3d_designer.app.QMessageBox.question',return_value=QMessageBox.No):self.w.offer_recovery()
        self.assertTrue(live.path.exists());self.assertFalse(self.w.dirty)
        options=self.w.recovery_options();self.assertEqual(options[0][0],live.path)
        with patch('e3d_designer.app.QInputDialog.getItem',return_value=(f'1. {options[0][1]}',True)):
            self.w.recover_work()
        self.assertEqual(self.w.form.title,'Live');self.assertTrue(self.w.dirty)
        other=RecoveryStore(self.folder/'recovery')
        self.assertEqual(other.candidates(),[])
        with patch('e3d_designer.app.QMessageBox.question',return_value=QMessageBox.Discard):self.w.new()
        self.assertFalse(live.path.exists());self.assertFalse(self.w.dirty)

    def test_incomplete_backup_and_write_errors_preserve_last_snapshot(self):
        w=self.w;w.form=Form(gadgets=[Gadget(kind='slider',name='level')]);w.dirty=True;w.refresh()
        w.backup_work();before=w.recovery.path.read_bytes()
        w.form.gadgets[0].slider_step=0
        w.backup_work();self.assertNotEqual(w.recovery.path.read_bytes(),before)
        restored,_=w.recovery.read(w.recovery.path)
        self.assertEqual(restored.gadgets[0].slider_step,0)
        with self.assertRaises(ValueError):restored.pml()
        before=w.recovery.path.read_bytes()
        w.form.gadgets[0].slider_step=1
        with patch('e3d_designer.recovery.os.replace',side_effect=OSError('read only')):w.backup_work()
        self.assertEqual(w.recovery.path.read_bytes(),before)
        self.assertEqual(len(list(w.recovery.directory.glob('*'))),2) # snapshot + session lock

    def test_corrupt_or_cancelled_recovery_keeps_current_state(self):
        w=self.w;w.add('button');before=w.form.dumps();history=len(w.history)
        corrupt=self.folder/'broken.json';corrupt.write_text('[]')
        with patch('e3d_designer.app.QMessageBox.warning') as warning:
            self.assertFalse(w.restore_work(corrupt));warning.assert_called_once()
        abandoned=self.abandoned()
        with patch('e3d_designer.app.QMessageBox.question',return_value=QMessageBox.Cancel):
            self.assertFalse(w.restore_work(abandoned.path))
        self.assertEqual(w.form.dumps(),before);self.assertEqual(len(w.history),history)
        self.assertTrue(w.dirty);self.assertTrue(abandoned.path.exists())

    def test_cancel_close_keeps_snapshot_and_confirmed_discard_cleans_own_only(self):
        w=self.w;foreign=self.abandoned();w.add('button');w.backup_work()
        with patch('e3d_designer.app.QMessageBox.question',return_value=QMessageBox.Cancel):w.close()
        self.assertTrue(w.recovery.path.exists());self.assertTrue(w.backup_timer.isActive())
        with patch('e3d_designer.app.QMessageBox.question',return_value=QMessageBox.Discard):w.close()
        self.assertFalse(w.recovery.path.exists());self.assertFalse(w.backup_timer.isActive())
        self.assertTrue(foreign.path.exists())
