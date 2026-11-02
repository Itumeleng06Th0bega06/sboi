from django.urls import path

from . import views

app_name = 'communications'

urlpatterns = [
    path('', views.inbox, name='inbox'),
    path(
        'conversations/',
        views.conversation_list,
        name='conversation_list',
    ),
    path(
        'conversation/<int:pk>/workspace/',
        views.conversation_workspace,
        name='conversation_workspace',
    ),
    path(
        'conversation/<int:pk>/messages/',
        views.conversation_messages,
        name='conversation_messages',
    ),
    path(
        'conversation/<int:pk>/send/',
        views.send_message,
        name='send_message',
    ),
    path(
        'conversation/<int:pk>/update/',
        views.update_group_view,
        name='update_group',
    ),
    path(
        'conversation/<int:pk>/members/add/',
        views.add_members_view,
        name='add_members',
    ),
    path(
        'conversation/<int:pk>/members/remove/',
        views.remove_member_view,
        name='remove_member',
    ),
    path(
        'conversation/<int:pk>/leave/',
        views.leave_group_view,
        name='leave_group',
    ),
    path('groups/create/', views.create_group_view, name='create_group'),
    path('direct/start/', views.start_direct_view, name='start_direct'),
    path(
        'attachments/<int:pk>/download/',
        views.download_attachment,
        name='download_attachment',
    ),
]
