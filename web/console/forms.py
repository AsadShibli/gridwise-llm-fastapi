"""Submit form: notes + optional full JSON (file or paste)."""

from django import forms


class RunForm(forms.Form):
    scenario_id = forms.CharField(max_length=128, initial="CONSOLE-01")
    note_1 = forms.CharField(widget=forms.Textarea, required=False)
    note_2 = forms.CharField(widget=forms.Textarea, required=False)
    note_3 = forms.CharField(widget=forms.Textarea, required=False)
    # Optional full POST body (same shape as hidden_posts/*.json).
    json_text = forms.CharField(widget=forms.Textarea, required=False)
    json_file = forms.FileField(required=False)

    def clean(self):
        cleaned = super().clean()
        notes = [
            cleaned.get("note_1") or "",
            cleaned.get("note_2") or "",
            cleaned.get("note_3") or "",
        ]
        has_notes = any(n.strip() for n in notes)
        has_json = bool((cleaned.get("json_text") or "").strip() or cleaned.get("json_file"))
        if not has_notes and not has_json:
            raise forms.ValidationError("Enter 1–3 notes, or upload/paste a full JSON body.")
        return cleaned
