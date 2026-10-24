"""Offline test of the stubborn-beat fix (pipeline/run_board.halves, 24 October): a beat Chatterbox garbles three reads
running is read again as two short sentences, cut at a comma or before a joining word, never mid-phrase."""
import pathlib as _p, sys as _s
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
_s.path.insert(0, REPO_DIR + "/pipeline")
import run_board as R

a, b = R.halves("If you watched the BBC's Amy Winehouse tribute, you saw Jorja Smith.")      # at the comma
assert a == "If you watched the BBC's Amy Winehouse tribute." and b == "You saw Jorja Smith.", (a, b)
a, b = R.halves("Jorja Smith is from Walsall, and that is where her story starts.")
assert a == "Jorja Smith is from Walsall." and b == "And that is where her story starts.", (a, b)
a, b = R.halves("The Guardian says she performed in a BBC TV show tribute to Amy Winehouse's Back to Black.")
assert a.endswith("tribute.") and b.startswith("To Amy"), (a, b)                              # before a joining word
assert R.halves("Short line here.") == ("", "")                                               # too short to split
assert R.halves("One two three four five six seven eight nine ten.") == ("", "")              # no natural place: left alone
a, b = R.halves("She began acting professionally at nine, and wrote her first book at nineteen.")
assert a.endswith("nine.") and b == "And wrote her first book at nineteen."
for t in ["A line, with a comma, in it and more words after that one.", "He went to the shop because the rain had stopped at last."]:
    a, b = R.halves(t)
    assert len(a.split()) >= 3 and len(b.split()) >= 3 and a[-1] in ".?!" and b[0].isupper(), (t, a, b)
print("voice split ok")
