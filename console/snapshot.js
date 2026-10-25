const CREW_SNAPSHOT = {
 "generated_at": "2026-10-25T18:33:27Z",
 "run_id": "accountable-crew/run-20261022T142807Z",
 "envelope_version": "cuni-audit-envelope/1",
 "checks": {
  "envelope_count": 12,
  "seq_contiguous_1_to_n": true,
  "required_keys_present": true,
  "distinct_envelope_signatures": true
 },
 "actions_seen": [
  "gate.decision",
  "hire.approved",
  "hire.claimed",
  "hire.posted",
  "hire.submitted",
  "mandate.delegated",
  "mandate.issued",
  "plan.created",
  "run.finished",
  "run.started",
  "x402.payment",
  "x402.terms"
 ],
 "seats": [
  {
   "agent_id": "253c5afe8b141faa",
   "actions": [
    "run.started",
    "gate.decision"
   ]
  },
  {
   "agent_id": "78a632ae52351538",
   "actions": [
    "run.started",
    "mandate.issued"
   ]
  }
 ],
 "mandates": [
  {
   "fingerprint": "5025bb5faa3549f8",
   "cap_cents": 100,
   "holder": "78a632ae52351538"
  }
 ],
 "decisions": [
  {
   "verdict": "ALLOW",
   "warrant_fingerprint": "e59bb39b3d1a28ed",
   "caller_agent_id": "253c5afe8b141faa",
   "cost_cents": 2
  }
 ],
 "receipts": [
  {
   "seq": 1,
   "action": "run.started",
   "verdict": "RECORDED",
   "issued_at": "2026-10-22T14:28:13Z",
   "fingerprint_sha256": "df257897308794464190e14c309f376190c345f37f4fa9d2c9457dd9364540e9",
   "envelope_signature": "b828906db643c3c7a528101094f4882fff6290b46e679c4d8589b8db5214623c34aaf3cd0ffed08ba645f879881274d6e675cbbcc713e74f99f0f3b16d1d1807"
  },
  {
   "seq": 2,
   "action": "mandate.issued",
   "verdict": "RECORDED",
   "issued_at": "2026-10-22T14:28:13Z",
   "fingerprint_sha256": "663d8a217d009aa063c2303dfc987a3e5bcd4a33270d8313aab78a099ef1bfdc",
   "envelope_signature": "e4419e0f348b7b1f27d1ea98224c6f6eebe4bc2ed15252eb1528c5ab9c45c57692bb361a2b6cd198a6bab2a843f51de694be309b768555ce6b92b4f644f0f601"
  },
  {
   "seq": 3,
   "action": "mandate.delegated",
   "verdict": "RECORDED",
   "issued_at": "2026-10-22T14:28:13Z",
   "fingerprint_sha256": "a88f7ddecb5acae5084804d556cadf8daf282244b70bcd1eb82549d438096d39",
   "envelope_signature": "986bb90c222d1ec1233f59b2ad1bf536959c78593b56cf2df8e2e3b45dec2ac8e12ee4ceae26d392783d593d01d686cc853f25527199d04531d8c41ece43bc08"
  },
  {
   "seq": 4,
   "action": "plan.created",
   "verdict": "RECORDED",
   "issued_at": "2026-10-22T14:28:13Z",
   "fingerprint_sha256": "f13f33f180bd23459e651365f52b9e7996455e6258addcd0bf8633b2fee51124",
   "envelope_signature": "84c821ec2aa58fd77d785c2850d6bacb967eaf26294f439a6deff0027c6b89557693f1f3756fcfb7e02fc33ab7d74330c03e2831425c4d27ca0985a6ab90a206"
  },
  {
   "seq": 5,
   "action": "hire.posted",
   "verdict": "RECORDED",
   "issued_at": "2026-10-22T14:28:15Z",
   "fingerprint_sha256": "f3f16d701390da5a87d781b7b153efd5a716c490539c37ae35a7e0758850fe8c",
   "envelope_signature": "0f7fd16dcfd27fe8455444b0ae76b04eeca72022b6a16f12365eb107a470f2cfe27837d45fa2b197ee5cbd6808fa6455404a7011fc564ceae36a7e5216ca2907"
  },
  {
   "seq": 6,
   "action": "hire.claimed",
   "verdict": "RECORDED",
   "issued_at": "2026-10-22T14:28:16Z",
   "fingerprint_sha256": "dd6c19f9b509e8ba2832b0cc75df3f0356d56834329c643937c2133460861fc6",
   "envelope_signature": "4c8c3932485240dd7a5868b05dbd247ee7f899e760581e66d83bff3b4c7c7850d45b1b6cf6779d6084bef336971e2c50df6793e48370c92ec8ea46cf4d963407"
  },
  {
   "seq": 7,
   "action": "x402.terms",
   "verdict": "RECORDED",
   "issued_at": "2026-10-22T14:28:17Z",
   "fingerprint_sha256": "1f3760cc8efdd93725d3394aa3310313c2448908821b362b1d99379722fc2be9",
   "envelope_signature": "d2a611d6b4592d73bd50863271eec90988df188766c9d4f598dc46b382e4572d677c5f6aac92ad2aef5e6ec16fbcd86b8f068fa33b9abbd284849012ff5fa40a"
  },
  {
   "seq": 8,
   "action": "gate.decision",
   "verdict": "ALLOW",
   "issued_at": "2026-10-22T14:28:17Z",
   "fingerprint_sha256": "0e98f5cdd7e4028c3694e01e3d488421f14e82ae73e40019ac6c53fe3b1bbf56",
   "envelope_signature": "df232b68985125155a466b78906ca2ee4769cba2693ab8a33be1cf70512bb80373fc32acec366fb211ca13ea1947501c4f9b3b200fddc3f0a4f88c33014ddb0a"
  },
  {
   "seq": 9,
   "action": "x402.payment",
   "verdict": "RECORDED",
   "issued_at": "2026-10-22T14:28:17Z",
   "fingerprint_sha256": "d971368935b4b01902ba25a1d7f377b7d04bca5f3f3ec62455fab69e2d672eb0",
   "envelope_signature": "96e1ad23edf44f4821b8bc92891d359894da99ce525925210f557eb5c588dfe89ab3500502ae6f157290ce549faa5edf02e429474947744d82d0e72d85e4c103"
  },
  {
   "seq": 10,
   "action": "hire.submitted",
   "verdict": "RECORDED",
   "issued_at": "2026-10-22T14:28:18Z",
   "fingerprint_sha256": "d53d2c85a3d243b8b98642fe610ffd84f44b90ced809882d07e85bf64ac224cc",
   "envelope_signature": "1299a75272d547684124b9f62abd5251ab28f03032e877dc2fab0fb039a20d9ebcaf250363fd455fb232342e3d9fc75f91940ccbf102d5ef536a746229f8060e"
  },
  {
   "seq": 11,
   "action": "hire.approved",
   "verdict": "RECORDED",
   "issued_at": "2026-10-22T14:28:20Z",
   "fingerprint_sha256": "4309199f080ce3385fb07024ac0b1f1e0f959a00e783e6f4759dc3dca0e53468",
   "envelope_signature": "c87f942b8d15b58eec8b05fa8cc4f9071e0ec884b028c6250fe782c50454baf4c5accad175f487ecb3c1859dc27298029b28eef3da665b1bf2d1d4d3c557fa03"
  },
  {
   "seq": 12,
   "action": "run.finished",
   "verdict": "RECORDED",
   "issued_at": "2026-10-22T14:28:22Z",
   "fingerprint_sha256": "8ed6af1b92ea9f077b09d9c4c2d1459d8d11c4b17fa4768e9a0f9e287fb837c3",
   "envelope_signature": "a456a3d3d6f1c00de3a3ce5dfeacc68d24ad36c1a2f606b113dd9f615a45c6da75062f2048412d9f0e8887e14d395e855c88da958a0d79b9b715bbfd47dcca04"
  }
 ],
 "tasks_open": [
  {
   "id": "tsk_f05965fb6ea14b79",
   "title": "Independent recount of a public cancer-research pack (wc + sha256)",
   "reward": 12,
   "category": "general"
  },
  {
   "id": "tsk_5577d99ab5e8e216",
   "title": "E2E desk post",
   "reward": 5,
   "category": "general"
  },
  {
   "id": "tsk_8116abc4ca521421",
   "title": "Create a data pipeline spec",
   "reward": 25,
   "category": "dev"
  },
  {
   "id": "tsk_77317a750dd45ccb",
   "title": "Classify code snippets by language",
   "reward": 8,
   "category": "classification"
  },
  {
   "id": "tsk_2339aaacfcfab9c4",
   "title": "Detect spam vs legitimate messages",
   "reward": 12,
   "category": "classification"
  },
  {
   "id": "tsk_8d0aece8c2455b08",
   "title": "Categorize GitHub issues by type",
   "reward": 10,
   "category": "classification"
  },
  {
   "id": "tsk_6b7fb943f0c34014",
   "title": "Tag support tickets by urgency",
   "reward": 12,
   "category": "classification"
  },
  {
   "id": "tsk_601aeda92f0e65c5",
   "title": "Classify 50 items into categories",
   "reward": 15,
   "category": "classification"
  },
  {
   "id": "tsk_9f4bfc72b722a260",
   "title": "Write a product description from bullet points",
   "reward": 10,
   "category": "nlp"
  },
  {
   "id": "tsk_3ebbb891b08eaac9",
   "title": "Score sentiment on reviews",
   "reward": 15,
   "category": "nlp"
  },
  {
   "id": "tsk_b4be2fa764a88b7e",
   "title": "Extract entities from an article",
   "reward": 12,
   "category": "nlp"
  },
  {
   "id": "tsk_f78c7409e4cac6f5",
   "title": "Translate text to Spanish",
   "reward": 12,
   "category": "nlp"
  },
  {
   "id": "tsk_e11c679a4ec0adff",
   "title": "Summarize a document",
   "reward": 10,
   "category": "nlp"
  }
 ],
 "verify": {
  "status": "pending-dep",
  "detail": "Cryptographic verify needs receipts.py + fabric-phase1 cuni_envelope (absent on this host). Structural checks above are local."
 }
};
