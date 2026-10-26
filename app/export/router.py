from datetime import date

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.export import service

router = APIRouter(tags=["Export"])


# "" rather than "/": the frontend calls /api/v1/export with no trailing
# slash. With "/" FastAPI would answer 307 to /api/v1/export/ — and behind
# Railway's proxy that redirect points at http://, which a page served over
# https refuses to follow.
@router.get(
    "",
    summary="Download every record you own, as JSON",
)
async def export_all_data(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    data = await service.export_user_data(current_user.user_id, current_user.email)
    filename = f"backendfinance-export-{date.today().isoformat()}.json"
    return JSONResponse(
        content=jsonable_encoder(data),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
