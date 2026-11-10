"""Members-only feed: shared by the admin workspace and the member account.

Everything here is scoped to signed-in accounts. Public visitors can never see
or fetch a post. Attachment downloads stream through this module so the private
storage directory is never exposed by the web server.
"""

import mimetypes
import re
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models_comms import (
    FEED_ATTACHMENT_EXTENSIONS,
    FEED_MAX_ATTACHMENT_SIZE,
    CommsAttachment,
    CommsComment,
    CommsPost,
    CommsPostSave,
    CommsReaction,
    CommsReport,
)
from .services import blocked_relationship_ids, interaction_blocked

FEED_PAGE_SIZE = 10

# A deliberately small first line of defence. The church office can still hide
# any post or comment; this only blocks obvious abuse from being published
# instantly, without pretending to be a full moderation service.
BLOCKED_TERMS = {
    'idiot', 'stupid', 'fool', 'hate you', 'kill you', 'shut up',
    'useless', 'damn you', 'bastard', 'bitch', 'asshole',
}


def _is_staff_user(user):
    return bool(user.is_staff or user.is_superuser)


def _clean_text(value, limit):
    return (value or '').replace('\x00', '').strip()[:limit]


def _moderation_error(*parts):
    combined = ' '.join(part.lower() for part in parts if part)
    combined = re.sub(r'\s+', ' ', combined)
    for term in BLOCKED_TERMS:
        if re.search(rf'\b{re.escape(term)}\b', combined):
            return (
                'Please keep the conversation respectful. '
                'That post or comment was not published.'
            )
    return ''


def can_view_post(user, post):
    """A single place for the feed's visibility rule."""
    if not post.is_published or post.is_hidden:
        return False
    if post.author_id and interaction_blocked(user, post.author_id):
        return False
    if _is_staff_user(user):
        return True
    return post.audience == CommsPost.AUDIENCE_ALL


def feed_posts_for(user):
    """Posts a given account may see, newest first."""
    queryset = (
        CommsPost.objects
        .filter(is_published=True, is_hidden=False)
        .select_related(
            'author',
            'author__member_profile',
            'shared_from',
            'shared_from__author',
            'shared_from__author__member_profile',
        )
        .prefetch_related(
            'attachments',
            'shared_from__attachments',
            'comments__author',
            'reactions',
            'saves',
            'shares',
            'shared_from__shares',
        )
    )
    hidden_ids = blocked_relationship_ids(user)
    if hidden_ids:
        queryset = queryset.exclude(author_id__in=hidden_ids)
    if not _is_staff_user(user):
        queryset = queryset.filter(audience=CommsPost.AUDIENCE_ALL)
    return queryset


def _reaction_summary(post, user, hidden_ids=None):
    hidden_ids = hidden_ids or set()
    rows = [
        row for row in post.reactions.all()
        if row.user_id not in hidden_ids
    ]
    counts = {}
    for row in rows:
        counts[row.reaction] = counts.get(row.reaction, 0) + 1
    mine = {row.reaction for row in rows if row.user_id == user.pk}
    return {
        'counts': counts,
        'mine': mine,
        'total': len(rows),
    }


def _author_avatar_url(post):
    author_profile = getattr(post.author, 'member_profile', None)
    if author_profile is not None and author_profile.avatar:
        try:
            return author_profile.avatar.url
        except ValueError:
            return ''
    return ''


def serialize_posts(posts, user):
    """Add reaction, save and comment summaries so templates stay logic-free."""
    staff = _is_staff_user(user)
    hidden_ids = blocked_relationship_ids(user)
    for post in posts:
        post.reaction_summary = _reaction_summary(post, user, hidden_ids)
        post.attachments_list = list(post.attachments.all())
        post.author_avatar_url = _author_avatar_url(post)
        post.saved_by_me = any(
            save.user_id == user.pk for save in post.saves.all()
        )
        root = post.shared_from if post.shared_from_id else post
        post.shared_by_me = any(
            share.author_id == user.pk for share in root.shares.all()
        )
        post.shared_from_visible = False
        if post.shared_from_id:
            shared = post.shared_from
            if can_view_post(user, shared):
                shared.author_avatar_url = _author_avatar_url(shared)
                shared.attachments_list = list(shared.attachments.all())
                post.shared_from_visible = True
        post.can_edit = post.author_id == user.pk and not post.is_hidden
        post.can_delete = staff or post.author_id == user.pk
        comments = [
            comment for comment in post.comments.all()
            if comment.author_id not in hidden_ids
        ]
        reply_map = {}
        roots = []
        for comment in comments:
            comment.replies_list = []
            comment.can_delete = (
                staff
                or comment.author_id == user.pk
                or post.author_id == user.pk
            )
            if comment.parent_id:
                reply_map.setdefault(comment.parent_id, []).append(comment)
            else:
                roots.append(comment)
        for comment in comments:
            comment.replies_list = reply_map.get(comment.pk, [])
        # ``comments_list`` stays flat for the staff workspace; the member
        # templates use ``comments_root`` to draw threaded replies.
        post.comments_list = comments
        post.comments_root = roots
        post.comment_count = len(comments)
    return posts


def feed_page(user, before=None, limit=FEED_PAGE_SIZE):
    """Return one page of posts plus whether another page exists."""
    return feed_page_for(feed_posts_for(user), user, before, limit)


def feed_page_for(queryset, user, before=None, limit=FEED_PAGE_SIZE):
    """Paginate any already-scoped feed queryset (feed, My posts, saved).

    The cursor is the last post's id, but posts are ordered by ``created_at``
    first. Filtering on ``pk`` alone would duplicate or skip posts whenever
    the id order and the timestamp order diverge, so resolve the cursor's
    timestamp and compare on the same ``(created_at, pk)`` tuple used for
    ordering.
    """
    if before:
        cursor = (
            CommsPost.objects
            .filter(pk=before)
            .values_list('created_at', flat=True)
            .first()
        )
        if cursor is None:
            queryset = queryset.filter(pk__lt=before)
        else:
            queryset = queryset.filter(
                Q(created_at__lt=cursor)
                | Q(created_at=cursor, pk__lt=before)
            )
    posts = list(queryset[:limit + 1])
    has_more = len(posts) > limit
    posts = posts[:limit]
    serialize_posts(posts, user)
    next_before = posts[-1].pk if posts else ''
    return posts, has_more, next_before


def _attachment_kind(file_name, content_type=''):
    suffix = Path(file_name).suffix.lower().lstrip('.')
    if suffix in {'jpg', 'jpeg', 'png', 'gif', 'webp'}:
        return CommsAttachment.KIND_IMAGE
    if (
        suffix in {'mp4', 'webm', 'mov', 'm4v'}
        or content_type.startswith('video/')
    ):
        return CommsAttachment.KIND_VIDEO
    return CommsAttachment.KIND_DOCUMENT


def _attachment_error(upload):
    if upload is None:
        return ''
    suffix = Path(upload.name).suffix.lower().lstrip('.')
    if suffix not in FEED_ATTACHMENT_EXTENSIONS:
        return (
            'That file type is not supported. Attach a photo, video, PDF or '
            'office document.'
        )
    if getattr(upload, 'size', 0) > FEED_MAX_ATTACHMENT_SIZE:
        return 'Attachments must be 25 MB or smaller.'
    return ''


def _store_attachment(post, upload):
    if upload is None:
        return None
    kind = _attachment_kind(
        upload.name, getattr(upload, 'content_type', '') or '',
    )
    return CommsAttachment.objects.create(
        post=post,
        file=upload,
        original_name=Path(upload.name).name[:255],
        content_type=(getattr(upload, 'content_type', '') or '')[:120],
        size=getattr(upload, 'size', 0) or 0,
        kind=kind,
    )


def _feed_redirect(user):
    if _is_staff_user(user):
        return reverse('communications:inbox') + '?view=feed'
    return reverse('members:account') + '#comms-feed'


def _member_style_surface(surface):
    return surface in {'community', 'admin_feed'}


def _render_post(request, post, surface='admin'):
    serialize_posts([post], request.user)
    template = (
        'members/account/_community_post.html'
        if _member_style_surface(surface)
        else 'admin/communications/_feed_post.html'
    )
    return render_to_string(
        template,
        {
            'post': post,
            'post_reaction_choices': CommsReaction.REACTION_CHOICES,
            'admin_community': surface == 'admin_feed',
        },
        request=request,
    )


def _render_comment(request, comment, post, surface='admin'):
    template = (
        'members/account/_community_comment.html'
        if _member_style_surface(surface)
        else 'admin/communications/_feed_comment.html'
    )
    return render_to_string(
        template,
        {
            'comment': comment,
            'post': post,
            'admin_community': surface == 'admin_feed',
        },
        request=request,
    )


def _surface(request):
    surface = request.POST.get('surface')
    if surface in {'community', 'admin_feed'}:
        return surface
    return 'admin'


@login_required
@require_POST
def feed_post_create(request):
    """Publish a post from the admin workspace or the member account."""
    title = _clean_text(request.POST.get('title'), 200)
    body = _clean_text(request.POST.get('body'), 8000)
    upload = request.FILES.get('attachment')

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    error = _moderation_error(title, body) or _attachment_error(upload)
    if not error and not (body or title or upload):
        error = 'Write something before posting.'

    if error:
        if is_ajax:
            return JsonResponse({'ok': False, 'message': error}, status=400)
        messages.error(request, error)
        return redirect(_feed_redirect(request.user))

    with transaction.atomic():
        post = CommsPost.objects.create(
            author=request.user,
            title=title,
            body=body,
            audience=CommsPost.AUDIENCE_ALL,
        )
        _store_attachment(post, upload)

    if is_ajax:
        return JsonResponse({
            'ok': True,
            'post_id': post.pk,
            'html': _render_post(request, post, _surface(request)),
        })
    return redirect(_feed_redirect(request.user))


@login_required
@require_POST
def feed_post_share(request, pk):
    """Repost an existing post to the signed-in member's own feed."""
    original = get_object_or_404(CommsPost, pk=pk)
    if not can_view_post(request.user, original):
        raise Http404('Post not found.')

    # Shares are one level deep: share the root post, never a repost.
    root = original.shared_from if original.shared_from_id else original
    if not can_view_post(request.user, root):
        raise Http404('Post not found.')

    post, created = CommsPost.objects.get_or_create(
        author=request.user,
        shared_from=root,
        defaults={'audience': root.audience},
    )
    message = (
        'Post shared to your feed.'
        if created
        else 'You already shared this post.'
    )
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'created': created,
            'post_id': post.pk,
            'message': message,
            'html': _render_post(request, post, _surface(request)) if created else '',
        })
    if created:
        messages.success(request, message)
    else:
        messages.info(request, message)
    return redirect(_feed_redirect(request.user))


@login_required
@require_POST
def feed_post_react(request, pk):
    post = get_object_or_404(CommsPost, pk=pk)
    if not can_view_post(request.user, post):
        raise Http404('Post not found.')

    reaction = request.POST.get('reaction', '')
    if reaction not in dict(CommsReaction.REACTION_CHOICES):
        reaction = CommsReaction.THUMB

    existing = CommsReaction.objects.filter(
        post=post, user=request.user, reaction=reaction,
    )
    if existing.exists():
        existing.delete()
        active = False
    else:
        # One reaction per person per post keeps the row tidy.
        CommsReaction.objects.filter(post=post, user=request.user).delete()
        CommsReaction.objects.create(
            post=post, user=request.user, reaction=reaction,
        )
        active = True

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        summary = _reaction_summary(post, request.user)
        return JsonResponse({
            'ok': True,
            'active': active,
            'summary': summary['counts'],
            'mine': sorted(summary['mine']),
        })
    return redirect(request.META.get('HTTP_REFERER') or _feed_redirect(request.user))


@login_required
@require_POST
def feed_post_comment(request, pk):
    post = get_object_or_404(CommsPost, pk=pk)
    if not can_view_post(request.user, post):
        raise Http404('Post not found.')

    body = _clean_text(request.POST.get('body'), 2000)
    error = _moderation_error(body)
    if not error and not body:
        error = 'Write a comment before sending.'

    if error:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'message': error}, status=400)
        messages.error(request, error)
        return redirect(request.META.get('HTTP_REFERER') or _feed_redirect(request.user))

    parent = None
    parent_id = request.POST.get('parent') or ''
    if parent_id.isdigit():
        parent = (
            CommsComment.objects
            .filter(pk=int(parent_id), post=post)
            .select_related('parent')
            .first()
        )
        # Keep the thread one level deep: a reply to a reply belongs to the
        # same root comment so the interface never nests endlessly.
        if parent is not None and parent.parent_id:
            parent = parent.parent

    comment = CommsComment.objects.create(
        post=post, author=request.user, body=body, parent=parent,
    )
    comment.replies_list = []
    comment.can_delete = True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'comment_id': comment.pk,
            'parent_id': parent.pk if parent else '',
            'count': post.comments.count(),
            'html': _render_comment(
                request, comment, post, _surface(request),
            ),
        })
    return redirect(request.META.get('HTTP_REFERER') or _feed_redirect(request.user))


@login_required
@require_POST
def feed_post_delete(request, pk):
    post = get_object_or_404(CommsPost, pk=pk)
    allowed = (
        _is_staff_user(request.user)
        or post.author_id == request.user.pk
    )
    if not allowed:
        raise PermissionDenied('You cannot remove this post.')
    post.delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect(request.META.get('HTTP_REFERER') or _feed_redirect(request.user))


@login_required
@require_POST
def feed_comment_delete(request, pk):
    comment = get_object_or_404(
        CommsComment.objects.select_related('post'), pk=pk,
    )
    allowed = (
        _is_staff_user(request.user)
        or comment.author_id == request.user.pk
        or comment.post.author_id == request.user.pk
    )
    if not allowed:
        raise PermissionDenied('You cannot remove this comment.')
    post = comment.post
    comment.delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'count': post.comments.count()})
    return redirect(request.META.get('HTTP_REFERER') or _feed_redirect(request.user))


@login_required
@require_POST
def feed_post_edit(request, pk):
    post = get_object_or_404(CommsPost, pk=pk)
    if post.author_id != request.user.pk:
        raise PermissionDenied('You can only edit your own posts.')
    title = _clean_text(request.POST.get('title'), 200)
    body = _clean_text(request.POST.get('body'), 8000)
    error = _moderation_error(title, body)
    if not error and not (body or title):
        error = 'Write something before saving.'

    if error:
        return JsonResponse({'ok': False, 'message': error}, status=400)

    post.title = title
    post.body = body
    post.edited_at = timezone.now()
    post.save(update_fields=['title', 'body', 'edited_at'])
    return JsonResponse({
        'ok': True,
        'message': 'Your post has been updated.',
        'html': _render_post(request, post, _surface(request)),
    })


@login_required
@require_POST
def feed_post_save(request, pk):
    post = get_object_or_404(CommsPost, pk=pk)
    if not can_view_post(request.user, post):
        raise Http404('Post not found.')
    existing = CommsPostSave.objects.filter(post=post, user=request.user)
    if existing.exists():
        existing.delete()
        saved = False
    else:
        CommsPostSave.objects.create(post=post, user=request.user)
        saved = True
    return JsonResponse({'ok': True, 'saved': saved})


@login_required
@require_POST
def feed_report(request):
    """Record a member report for a post or a comment."""
    reason = request.POST.get('reason', '')
    if reason not in dict(CommsReport.REASON_CHOICES):
        reason = CommsReport.REASON_OTHER
    note = _clean_text(request.POST.get('note'), 1000)
    post = None
    comment = None
    post_id = request.POST.get('post_id') or ''
    comment_id = request.POST.get('comment_id') or ''
    if post_id.isdigit():
        post = get_object_or_404(CommsPost, pk=int(post_id))
        if not can_view_post(request.user, post):
            raise Http404('Post not found.')
    elif comment_id.isdigit():
        comment = get_object_or_404(
            CommsComment.objects.select_related('post'), pk=int(comment_id),
        )
        post = comment.post
        if not can_view_post(request.user, post):
            raise Http404('Comment not found.')
    else:
        return JsonResponse({
            'ok': False,
            'message': 'Choose something to report.',
        }, status=400)

    report, created = CommsReport.objects.get_or_create(
        post=post if comment is None else None,
        comment=comment,
        reporter=request.user,
        defaults={'reason': reason, 'note': note},
    )
    if not created:
        # A second report from the same member updates their reason rather
        # than filling the moderation queue with duplicates.
        report.reason = reason
        report.note = note
        report.status = CommsReport.STATUS_PENDING
        report.save(update_fields=['reason', 'note', 'status'])
    return JsonResponse({
        'ok': True,
        'message': 'Thank you. The church office will review this.',
    })


@login_required
@require_GET
def feed_load_more(request):
    before = (request.GET.get('before') or '').strip()
    before_id = int(before) if before.isdigit() else None
    scope = request.GET.get('scope') or 'feed'
    if scope == 'posts':
        posts, has_more, next_before = feed_page_for(
            feed_posts_for(request.user).filter(author=request.user),
            request.user,
            before=before_id,
        )
    elif scope == 'saved':
        posts, has_more, next_before = feed_page_for(
            feed_posts_for(request.user).filter(saves__user=request.user),
            request.user,
            before=before_id,
        )
    else:
        posts, has_more, next_before = feed_page(
            request.user, before=before_id,
        )
    html = render_to_string(
        'members/account/_community_feed_items.html',
        {
            'posts': posts,
            'post_reaction_choices': CommsReaction.REACTION_CHOICES,
            'admin_community': request.GET.get('surface') == 'admin_feed',
        },
        request=request,
    )
    return JsonResponse({
        'ok': True,
        'html': html,
        'has_more': has_more,
        'next_before': next_before,
    })


@login_required
@require_GET
def feed_attachment_download(request, pk):
    attachment = get_object_or_404(
        CommsAttachment.objects.select_related('post', 'post__author'),
        pk=pk,
    )
    post = attachment.post
    if not can_view_post(request.user, post):
        raise Http404('Attachment not found.')

    try:
        file_handle = attachment.file.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404('The attachment is no longer available.')

    filename = attachment.original_name or Path(attachment.file.name).name
    guessed = mimetypes.guess_type(filename)[0]
    inline = (
        request.GET.get('inline') == '1'
        and attachment.kind in {
            CommsAttachment.KIND_IMAGE, CommsAttachment.KIND_VIDEO,
        }
    )
    response = FileResponse(
        file_handle,
        as_attachment=not inline,
        filename=filename,
        content_type=guessed or attachment.content_type or 'application/octet-stream',
    )
    response['X-Content-Type-Options'] = 'nosniff'
    if inline:
        response['Cache-Control'] = 'private, max-age=3600'
    return response


@login_required
@require_GET
def feed_poll(request):
    """Lightweight JSON refresh so both workspaces see new posts."""
    queryset = feed_posts_for(request.user)
    latest = queryset.values_list('pk', flat=True).first()
    return JsonResponse({
        'ok': True,
        'count': queryset.count(),
        'latest_id': latest,
        'server_time': timezone.now().isoformat(),
    })
