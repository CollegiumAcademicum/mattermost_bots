"""Result view — step 3 of 3."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


@login_required
def result(request):
    result_data = request.session.pop("broadcast_result", None)
    if result_data is None:
        return redirect("broadcast:compose")
    return render(request, "broadcast/result.html", {"result": result_data})
