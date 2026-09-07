import json
import logging
from datetime import datetime

class JsonFormatter(logging.Formatter):
    EXTRA_FIELDS = (
        "event",
        "correlation_id",
        "method",
        "path",
        "result",
        "activity_id",   ##para saber porq la respuesta cambia de 201 a 200 sin crear otra inscripcion
        "participant_id",
        
        )
    
    def format(self, record):
        payload={
            "timestamp": datetime.fromtimestamp(
                record.created
                ).astimezone().isoformat(),
            "level":record.levelname.lower(),
            "event":getattr(record,"event",record.getMessage()),
            "message":record.getMessage(),
        }
        for field in self.EXTRA_FIELDS:
            if hasattr(record,field):
                payload[field]=getattr(record,field)
        return json.dumps(payload, ensure_ascii=False)