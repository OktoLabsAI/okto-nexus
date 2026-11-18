# SI-013 dashboard intake for an exact session

The authenticated dashboard runtime route reads the technical next-turn
revision for one exact session. With the startup gate enabled, an active
human operator can post a typed input to that scope. The server derives
the author from the current login cookie, applies the canonical session and
grant checks, and returns the durable input receipt. The send goes through
the session coordinator and R4, with a native user prompt at the executor.

The receipt endpoint reads by the original client intent, exact scope and
human login. An absent receipt is 404 and creates no login reference or
work. The request-validation response omits the submitted body. Data stays
in the existing store. Reverting the routes leaves the queue and journal
available to a compatible build.

The API integration uses a synthetic peer and a temporary store. It
exercises the required human login, origin, scope and capability checks,
stable duplicate input, read-only recovery, a different login and logout.
The serve, receipt and transport contract run passed 24 cases.
The composer, keyboard interaction and browser campaign remain pending.
