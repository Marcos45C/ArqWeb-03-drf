import uuid

import logging

logger = logging.getLogger("app.http")


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        #-----antes de ejecutar el view
        correlation_id =(
            request.headers.get("X-Correlation-ID")
            or str(uuid.uuid4())
        )
        request.correlation_id = correlation_id

        common_fields={
            "correlation_id": correlation_id,
            "method": request.method,
            "path": request.path,
        }

        logger.info(
                "request_received",
                extra={
                    "event": "request_received",
                    "result":"received",
                    **common_fields,  
                    }
        )


        #----- Despues de ejecutar el view
        response = self.get_response(request)
        response["X-Correlation-ID"] = correlation_id

        logger.info(
                        "request_completed",
                        extra={
                            "event": "request_completed",
                            "result":"str(response.status_code)",
                            **common_fields,  
                            },
                )
        
        return response