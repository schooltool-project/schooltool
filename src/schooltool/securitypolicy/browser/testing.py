
from schooltool.securitypolicy.metaconfigure import getDescriptionUtility


def discriminator_sort_key(disc):
    if disc[1] is None:
        return ('', 'None', disc[0])
    return (str(disc[1].__module__), str(disc[1].__name__), disc[0])


def collectActionsByDiscriminator():
    util = getDescriptionUtility()
    collected = {}
    for group in util.actions_by_group.values():
        for action in group.values():
            discriminator = (action.permission, action.interface)
            if discriminator not in collected:
                collected[discriminator] = []
            collected[discriminator].append(action)
    for actions in collected.values():
        actions[:] = sorted(actions,
                            key=lambda a: a.__name__ + a.__parent__.__name__)
    return collected


def printActionDescriptions(actions_by_discriminator):
    last_module = ''
    util = getDescriptionUtility()
    for disc in sorted(actions_by_discriminator, key=discriminator_sort_key):
        mod, ifc, perm = discriminator_sort_key(disc)
        if mod != last_module:
            last_module = mod
            print '=' * len(last_module)
            print last_module
            print '=' * len(last_module)
        perm_pair_desc = '%s, %s' % (ifc, perm)
        print '- %s\n- %s' % (perm_pair_desc, '-' * len(perm_pair_desc))
        listed = [
            str('%s / %s' % (util.groups[a.__parent__.__name__].title,
                             a.title))
            for a in actions_by_discriminator[disc]]
        for act in listed:
            print '-  %s' % act
        print '-'


def printDiscriminators(discriminators):
    last_module = ''
    for disc in sorted(discriminators, key=discriminator_sort_key):
        mod, ifc, perm = discriminator_sort_key(disc)
        if mod != last_module:
            last_module = mod
            print '-' * len(last_module)
            print last_module
            print '-' * len(last_module)
        print '%s, %s' % (ifc, perm)
