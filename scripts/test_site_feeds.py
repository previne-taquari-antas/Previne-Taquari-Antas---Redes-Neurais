import json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from scripts.audit_site_feeds import audit
class FeedHealthTests(unittest.TestCase):
 def test_brt_observation_and_query_are_independent(self):
  with tempfile.TemporaryDirectory() as d:
   Path(d,'previsao_ao_vivo.json').write_text(json.dumps({'consultado_em':'2026-10-21T09:00:00','nivel_rio_agora_em':'2026-10-21T06:00:00'}))
   rows={r['path']:r for r in audit(d,datetime(2026,10,21,12,tzinfo=timezone.utc))['sources']}
   self.assertEqual(rows['previsao_ao_vivo.json']['state'],'CURRENT')
   self.assertEqual(rows['previsao_ao_vivo.json#observed']['state'],'STALE')
   self.assertEqual(rows['previsao_ao_vivo.json#observed']['age_hours'],3)
   self.assertEqual(rows['previsao_ao_vivo_mucum.json']['state'],'UNAVAILABLE')
 def test_future_timestamp_is_not_current(self):
  with tempfile.TemporaryDirectory() as d:
   Path(d,'previsao_ao_vivo.json').write_text(json.dumps({'consultado_em':'2099-01-01T00:00:00Z'}))
   rows=audit(d)['sources'];self.assertTrue(any(r['state']=='FUTURE_TIMESTAMP' for r in rows))
if __name__=='__main__':unittest.main()
