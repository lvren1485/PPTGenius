"""Test workspace manager (singleton)."""
import shutil
import tempfile

from pptgenius.infrastructure.workspace.manager import WorkspaceManager


class TestWorkspaceManager:
    @classmethod
    def setup_class(cls):
        cls.tmp = tempfile.mkdtemp()
        # Override root via constructor (first call sets the singleton)
        cls.wm = WorkspaceManager(root=cls.tmp)

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_singleton(self):
        wm2 = WorkspaceManager()
        assert wm2 is self.wm

    def test_create(self):
        p = self.wm.create(1)
        assert p.exists()
        assert (p / "input").exists()
        assert (p / "knowledge").exists()
        assert (p / "output").exists()

    def test_get_path(self):
        p = self.wm.get_path(42)
        assert p.name == "42"

    def test_get_dirs(self):
        self.wm.create(99)
        assert self.wm.get_input_dir(99).name == "input"
        assert self.wm.get_knowledge_dir(99).name == "knowledge"
        assert self.wm.get_output_dir(99).name == "output"

    def test_clean(self):
        self.wm.create(7)
        assert self.wm.get_path(7).exists()
        self.wm.clean(7)
        assert not self.wm.get_path(7).exists()
