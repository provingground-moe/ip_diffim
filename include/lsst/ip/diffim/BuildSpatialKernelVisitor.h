// -*- lsst-c++ -*-
/**
 * @file BuildSpatialKernelVisitor.h
 *
 * @brief Declaration of BuildSpatialKernelVisitor 
 *
 * @author Andrew Becker, University of Washington
 *
 * @ingroup ip_diffim
 */

#ifndef LSST_IP_DIFFIM_BUILDSPATIALKERNELVISITOR_H
#define LSST_IP_DIFFIM_BUILDSPATIALKERNELVISITOR_H

#include "Eigen/Core"
#include "lsst/afw/math.h"
#include "lsst/afw/image.h"
#include "lsst/ip/diffim.h"
#include "lsst/pex/policy/Policy.h"

namespace lsst { 
namespace ip { 
namespace diffim { 
namespace detail {

    template<typename PixelT>
    class BuildSpatialKernelVisitor : public lsst::afw::math::CandidateVisitor {
    public:
        typedef boost::shared_ptr<BuildSpatialKernelVisitor<PixelT> > Ptr;

        BuildSpatialKernelVisitor(
            lsst::afw::math::KernelList const& basisList,  ///< Basis functions
            lsst::pex::policy::Policy policy         ///< Policy file directing behavior
            );

        int getNCandidates() {return _nCandidates;}

        void processCandidate(lsst::afw::math::SpatialCellCandidate *candidate);

        void solveLinearEquation();

        std::pair<lsst::afw::math::LinearCombinationKernel::Ptr, 
                  lsst::afw::math::Kernel::SpatialFunctionPtr> getSolutionPair();

    private:
        boost::shared_ptr<SpatialKernelSolution> _kernelSolution;
        int _nCandidates;                  ///< Number of candidates visited
    };

    template<typename PixelT>
    boost::shared_ptr<BuildSpatialKernelVisitor<PixelT> >
    makeBuildSpatialKernelVisitor(
        lsst::afw::math::KernelList const& basisList,
        lsst::pex::policy::Policy policy
        ) {

        return typename BuildSpatialKernelVisitor<PixelT>::Ptr(
            new BuildSpatialKernelVisitor<PixelT>(basisList, policy)
            );
    }

}}}} // end of namespace lsst::ip::diffim::detail

#endif