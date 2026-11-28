"""Exact, versioned browser contracts, separate from the CLI HTTP transport.

Production registration is deliberately explicit. The distributed broker catalog
currently contains manual procedures, not qualified automatic browser contracts.
"""
import json
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class BrowserProcedure:
    identifier: str
    version: str
    page_url: str
    submit_url: str
    form_id: str
    button_id: str
    fields: tuple  # pairs of fixed HTML field name and session identifier category
    success_id: str
    success_text: str
    effect: str

    @property
    def inspect_script(self):
        return r"""(() => {
 const f=document.getElementById(FORM), b=document.getElementById(BUTTON);
 if (!f || !b || b.form!==f) return null;
 return {page:location.href, action:f.action, method:f.method.toLowerCase(),
 fields:[...f.elements].filter(e=>e.name && !['submit','button'].includes(e.type)).map(e=>({name:e.name,type:e.type})),
 challenge:!!document.querySelector('iframe[src*=captcha],input[type=password],[data-sitekey]'),
 button:b.id};
})()""".replace("FORM", json.dumps(self.form_id)).replace("BUTTON", json.dumps(self.button_id))

    def accepts(self, contract):
        return (isinstance(contract, dict) and not contract.get("challenge")
                and contract.get("page") == self.page_url and contract.get("action") == self.submit_url
                and contract.get("method") == "post" and contract.get("button") == self.button_id
                and sorted((f.get("name"), f.get("type")) for f in contract.get("fields", []))
                == sorted((name, "email" if category == "email" else "text") for name, category in self.fields)
                and urlsplit(self.page_url).netloc == urlsplit(self.submit_url).netloc)

    def submit_script(self, values):
        expected = {"page": self.page_url, "action": self.submit_url, "method": "post",
                    "fields": [{"name": name, "type": "email" if category == "email" else "text"} for name, category in self.fields],
                    "challenge": False, "button": self.button_id}
        return """(() => {
 const observed=INSPECT;
 const canonical = v => v && typeof v==='object' ? Array.isArray(v) ? v.map(canonical).sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b))) : Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])) : v;
 if(JSON.stringify(canonical(observed))!==JSON.stringify(canonical(EXPECTED))) return false;
 const f=document.getElementById(FORM), b=document.getElementById(BUTTON);
 for(const [k,v] of Object.entries(VALUES)) f.elements.namedItem(k).value=v;
 if(!f.checkValidity()) return false;
 f.requestSubmit(b); return true;
})()""".replace("INSPECT", self.inspect_script).replace("EXPECTED", json.dumps(expected)).replace("FORM", json.dumps(self.form_id)).replace("BUTTON", json.dumps(self.button_id)).replace("VALUES", json.dumps({name: values[category] for name, category in self.fields}))

    def completed(self, snapshot):
        # An arbitrary 'thank you' string elsewhere in the page is not sufficient.
        return (snapshot.get("url") == self.submit_url and not snapshot.get("challenge")
                and snapshot.get("completion_id") == self.success_id
                and snapshot.get("completion_text") == self.success_text)


# Never infer permission to submit from the presence of a generic HTML form.
# Add a real adapter only after reviewing its official procedure and qualification.
QUALIFIED_PROCEDURES = {}
