import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools/freddi_fisk"
sys.path.insert(0, str(TOOLS))
import prepare_shark_datasets as sharks
sys.path.remove(str(TOOLS))


class SharkCueTests(unittest.TestCase):
    def references(self, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        source = Path(tmp.name) / "cutscene.scu"
        source.write_text(text)
        specification = {"cutscene.scu": {"sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                         "scripts": {"200": {"154": "boss", "147": "spongehead"}}}}
        return sharks.dialogue_refs(tmp.name, specification)

    def test_shared_actor_changes_character_by_explicit_dialogue_color(self):
        refs = self.references('script 200 {\nactor 2 \\\n talk-color 154 \\\n talkie 1 "@T10,20@Boss line"\\\n talk-color 147 \\\n talkie 2 "@T30,40@Other shark"\\\n\n}\n')
        self.assertEqual(refs[10][0]["speaker"], "boss")
        self.assertEqual(refs[30][0]["speaker"], "spongehead")

    def test_squidfather_other_scripts_and_inherited_colors_are_excluded(self):
        refs = self.references('script 200 {\nactor 3 \\\n talk-color 162 \\\n talkie 1 "@T10,20@Grumble"\\\n\nactor 2 \\\n talk-color 154 \\\n talkie 2 "@T30,40@Boss"\\\n\nactor 2 \\\n talkie 3 "@T50,20@Uncertain"\\\n\n}\nscript 201 {\nactor 2 \\\n talk-color 154 \\\n talkie 1 "@T70,20@Unrelated scene"\\\n\n}\n')
        self.assertEqual(set(refs), {30})

    def test_changed_cutscene_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "scene.scu").write_text("modified source")
            with self.assertRaisesRegex(ValueError, "Unverified cutscene"):
                sharks.dialogue_refs(tmp, {"scene.scu": {"sha256": "wrong", "scripts": {}}})


if __name__ == "__main__":
    unittest.main()
