from django.shortcuts import render
from django.http import HttpResponse


# Create your views here.
def error(request):
    raise Exception('test')
