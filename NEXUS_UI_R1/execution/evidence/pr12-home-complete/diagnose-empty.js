async page=>await page.evaluate(async()=>await(await fetch('/api/v1/home/entries?workspace_id=ws&limit=10&preview=3')).json())
